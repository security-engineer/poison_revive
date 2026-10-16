# 실제 MCP 클라이언트가 실패한 tool call을 모델에 넘기는 방식 (2026-10-10 조사)

## 0. 조사 방법과 범위

- 모델 호출, MCP 서버 실행, Docker 실행은 하지 않았다. 아래의 "모델이 보는 텍스트" 예시는 실행해서 관찰한 것이 아니라 코드에서 조립한 것이다. 오류 문구는 `Error: tool execution failed`로 두었다.
- 오픈소스 4종은 release tag에서 shallow clone한 뒤 소스를 직접 읽었다. 인용 URL은 모두 아래 commit에 고정돼 있다. 줄 번호도 그 commit 기준이다.

| 클라이언트 | 기준 | commit | 커밋 시각 |
|---|---|---|---|
| Gemini CLI (`google-gemini/gemini-cli`) | tag `v0.63.0` | `573846625af9e93b3b968e0e0b86bb093a4c9b16` | 2026-10-06 |
| Codex CLI (`openai/codex`, `codex-rs`) | tag `rust-v0.162.1` | `092d3acd6bec3e3a14bdc7e7a2810ab628ab759d` | 2026-10-09 |
| fast-agent (`evalstate/fast-agent`) | tag `v0.10.43` | `e67667601ca59eeb4cf4d28a732e7dc39a8fd034` | 2026-10-07 |
| mcp-agent (`lastmile-ai/mcp-agent`) | `main` HEAD (pyproject `0.2.6`) | `f62d849350816588b1c6294e7914bbe4d8b84072` | 2026-01-25 (이후 커밋 없음) |

- URL 접두어:
  - GEM = `https://github.com/google-gemini/gemini-cli/blob/573846625af9e93b3b968e0e0b86bb093a4c9b16/`
  - CDX = `https://github.com/openai/codex/blob/092d3acd6bec3e3a14bdc7e7a2810ab628ab759d/codex-rs/`
  - FA = `https://github.com/evalstate/fast-agent/blob/e67667601ca59eeb4cf4d28a732e7dc39a8fd034/`
  - MA = `https://github.com/lastmile-ai/mcp-agent/blob/f62d849350816588b1c6294e7914bbe4d8b84072/`
  - 예: `GEM packages/core/src/tools/mcp-tool.ts#L456-L470` → `https://github.com/google-gemini/gemini-cli/blob/5738466…/packages/core/src/tools/mcp-tool.ts#L456-L470`
- Claude Code, Claude Desktop, Cursor는 소스가 공개되지 않았다. 공식 문서만 근거로 썼고, 해당 절마다 그렇게 적었다. 문서 문장은 원문을 그대로 인용했다(Claude Code와 Cursor 문장은 raw 페이지에서 다시 grep해 확인했다).
- 표기:
  - **[CODE]**: 소스에서 직접 확인.
  - **[DOCS]**: 공식 문서 원문.
  - **[DERIVED]**: 코드를 조합해 추론했고 실행하지 않음.
  - **UNVERIFIED**: 확인하지 못함.

## 1. 핵심 결론

1. **오픈소스 4종 모두 `isError` 결과에 지시문이나 해결책(remedy) 문구를 붙이지 않는다.** [CODE]
   - 서버의 오류 텍스트는 그대로 전달된다.
   - Gemini CLI만 중립적인 클라이언트 문장 한 줄과 raw JSON으로 감싼다.
   - 클라이언트가 직접 쓴 remedy 비슷한 문구는 fast-agent에 하나뿐이다. 세션이 끊긴 뒤 재연결까지 실패한 예외 경로의 "Please check server status or try again later."다.
2. **`isError` 플래그가 모델에게 보이는지는 클라이언트보다 provider wire format에 달려 있다.** [CODE]
   - OpenAI Chat Completions의 `role:"tool"`와 Responses API의 `function_call_output`에는 오류 필드가 없다. 그래서 Codex, fast-agent의 OpenAI 계열, mcp-agent의 OpenAI 계열에서는 플래그가 사라지고 텍스트만 남는다.
   - Anthropic `tool_result.is_error`(native)는 fast-agent와 mcp-agent가 전달한다.
   - Gemini `functionResponse.response.error` 키(provider 규약)는 Gemini CLI, fast-agent, mcp-agent가 쓴다.
   - **우리 실험 대상인 Qwen3-14B와 gpt-oss-20b를 OpenAI 호환 endpoint(vLLM)로 붙이면, 조사한 클라이언트에서는 E_unknown과 비슷한 평문만 남는다.**
3. **모든 클라이언트가 오류 뒤에도 agent loop를 계속 돌려, 다시 호출할지는 모델이 정한다.** [CODE]
   - 실패한 `tools/call`을 클라이언트가 자동으로 다시 실행하는 경우는 둘뿐이다. fast-agent의 세션 종료 후 reconnect·replay(설정에 따름)와 Claude Code의 401/403 재시도 1회 [DOCS]다.
   - 즉 오류 재활성화가 일어날 수 있는 조건(모델이 다음 호출을 정함)이 조사한 모든 클라이언트에 있다.
4. **transport·timeout 예외도 모두 오류 결과로 바뀌어 모델에게 전달된다.** [CODE] loop를 중단시키지 않는다. 앞에 클라이언트가 접두어를 붙인다(`tool call error: …`, `Failed to call_tool '…' on server '…': …` 등).
5. **"한 라운드 뒤 강제 요약"(reference-chatbot과 비슷한 형태)을 기본으로 하는 클라이언트는 없다.**
   - 코드상 가장 가까운 것은 mcp-agent의 Anthropic·Bedrock 경로다. 마지막 iteration(기본 `max_iterations=10`)에서 "We've reached the maximum number of iterations. Please stop using tools now and provide your final comprehensive answer…"라는 user 메시지를 넣는다.
6. **명세가 `isError`를 "자기 교정 후 재시도" 채널로 설계했다.** [DOCS]
   - MCP 2025-11-25 `server/tools.mdx`: "Tool Execution Errors contain actionable feedback that language models can use to self-correct and retry with adjusted parameters." / "Clients **SHOULD** provide tool execution errors to language models to enable self-correction."
   - `schema.ts`의 `isError` 주석: "Otherwise, the LLM would not be able to see that an error occurred and self-correct."
   - 출처: `https://github.com/modelcontextprotocol/modelcontextprotocol/blob/c518f7a927cff918bce35d3522fcdb046d264d7c/docs/specification/2025-11-25/server/tools.mdx#L460-L477`, `schema/2025-11-25/schema.ts#L1115-L1129`
   - Anthropic tool-use 문서(`platform.claude.com/docs/en/agents-and-tools/tool-use/handle-tool-calls`)는 서버 작성자에게 remedy를 넣으라고 권한다: "Write instructive error messages. Instead of generic errors like `"failed"`, include what went wrong and what Claude should try next (for example, `"Rate limit exceeded. Retry after 60 seconds."`)." 또 "If a tool request is invalid or missing parameters, Claude will retry 2-3 times with corrections before apologizing to the user."라고 적혀 있다.
   - 따라서 remedy-added 조건은 클라이언트 기본값이 아니다. 서버 작성자나 운영자 쪽 관행(그리고 Claude Code hook)에 해당한다.

---

## 2. Gemini CLI (v0.63.0) [CODE]

### (1) `isError=true`일 때 모델이 받는 것

- `McpCallableTool.callTool`이 SDK의 `CallToolResult`를 손대지 않고 `[{functionResponse:{name, response: result}}]`로 감싼다(`GEM packages/core/src/tools/mcp-client.ts#L1436-L1492`).
- `DiscoveredMCPToolInvocation.isMCPToolError`가 오류를 판정한다(`GEM packages/core/src/tools/mcp-tool.ts#L389-L413`). 두 경우가 해당한다.
  - 최상위 `isError === true || 'true'`
  - legacy 형태인 `response.error.isError`
- 오류이면 `execute`가 다음 문자열을 만든다(`mcp-tool.ts#L456-L470`).
  ```ts
  `MCP tool '${serverToolName}' reported tool error for function call: ${safeJsonStringify(functionCalls[0])} with response: ${safeJsonStringify(rawResponseParts)}`
  ```
  - `error.type = MCP_TOOL_ERROR`가 붙는다.
  - 사용자 화면에는 `Error: MCP tool '<name>' reported an error.`만 보인다.
  - `safeJsonStringify`는 공백 없는 compact JSON을 만든다(`packages/core/src/utils/safeJsonStringify.ts#L16-L34`).
- scheduler가 `toolResult.error`를 보고 `createErrorResult` → `createErrorResponse`로 넘긴다. 모델용 part는 `functionResponse {id, name, response: { error: error.message }}`가 된다(`GEM packages/core/src/scheduler/tool-executor.ts#L150-L167`, `#L560-L583`).
  - 성공이면 `{output: "<text>"}`가 된다(`packages/core/src/utils/generateContentResponseUtilities.ts#L136`).
  - `output`/`error` 키는 Gemini API 규약이다. `@google/genai`의 `FunctionResponse.response` 주석: "Use "output" key to specify function output and "error" key to specify error details (if any)." (`googleapis/js-genai` `src/types.ts#L2100`, main `2cdb3b2`)
- 모델이 보는 형태 [DERIVED]:
  ```json
  {"functionResponse":{"id":"<callId>","name":"<tool>","response":{"error":
   "MCP tool 'read_file' reported tool error for function call: {\"name\":\"read_file\",\"args\":{\"path\":\"a.txt\"}} with response: [{\"functionResponse\":{\"name\":\"read_file\",\"response\":{\"content\":[{\"type\":\"text\",\"text\":\"Error: tool execution failed\"}],\"isError\":true}}}]"}}}
  ```
- 판단:
  - 서버의 오류 텍스트는 그대로 들어가지만 JSON escape된 채 안쪽에 있다.
  - `"isError":true`가 들어간 raw `CallToolResult` JSON이 그대로 노출된다.
  - 클라이언트가 붙이는 것은 "reported tool error for function call … with response …"라는 설명문뿐이다. 지시나 remedy는 없다.
  - UNVERIFIED: 직렬화된 `CallToolResult`의 키 순서와 추가 필드(`structuredContent`, `_meta`)는 서버 응답과 TS SDK의 parsing에 따라 달라진다.

### (2) 예외(transport, protocol, timeout)

- `callTool`의 `catch`가 모든 예외를 `{functionResponse:{name, response:{error:{message, isError:true}}}}`로 바꾼다(`mcp-client.ts#L1472-L1486`).
- 이 형태는 위의 legacy 판정에 걸려, (1)과 같은 설명문 wrapper로 전달된다.
- [DERIVED] 모델이 보는 `response.error` 값:
  ```
  MCP tool 'X' reported tool error for function call: {...} with response: [{"functionResponse":{"name":"X","response":{"error":{"message":"MCP error -32001: Request timed out","isError":true}}}}]
  ```
- timeout 관련 값:
  - 기본 timeout은 `MCP_DEFAULT_TIMEOUT_MSEC = 10 * 60 * 1000`이다(`mcp-client.ts#L96`).
  - 오류 문구는 TS SDK 1.23.0(`packages/core/package.json#L34`)에서 온다. `McpError` 생성자가 `` `MCP error ${code}: ${message}` ``를 만들고, timeout이면 `'Request timed out'`(code -32001)을 쓴다(`modelcontextprotocol/typescript-sdk` tag `1.23.0`, `src/types.ts#L1771-L1779`, `src/shared/protocol.ts#L576`).
- 사용자 abort는 `'Tool call aborted'`(AbortError)가 되고 cancelled 경로로 간다. 이 경우 `Operation cancelled.`(`tool-executor.ts#L176-L183`).
- 그 밖의 예외는 `UNHANDLED_EXCEPTION`, `{error: error.message}`가 된다(`#L184-L192`).
- 시사점: `isError` 결과와 예외 결과는 겉 wrapper가 같다. 안쪽 JSON 모양(`content`+`isError` 대 `error.message`+`isError`)만 다르다.

### (3) 재시도와 loop

- `tools/call`을 자동으로 다시 실행하지 않는다. `mcp-client.ts`의 retry는 목록 refresh(`#L540`, `#L639`, `#L749`)와 OAuth에만 쓰인다.
- loop는 계속된다.
  - interactive: `useGeminiStream.handleCompletedTools`가 오류를 포함한 모든 `responseParts`를 `isContinuation: true`로 다시 보낸다(`GEM packages/cli/src/ui/hooks/useGeminiStream.ts#L2149-L2194`). 멈추는 경우는 `STOP_EXECUTION`과 전체 취소뿐이다.
  - non-interactive: `LegacyAgentSession`이 `STOP_EXECUTION`과 fatal 오류에서만 멈춘다(`packages/core/src/agent/legacy-agent-session.ts#L325-L343`). fatal은 `NO_SPACE_LEFT` 하나다(`packages/core/src/tools/tool-error.ts#L101-L109`).
- system prompt에 일반적인 독려 문장이 있다: "persist through errors and obstacles by diagnosing failures in the execution phase…"(`packages/core/src/prompts/snippets.ts#L259`). 오류마다 붙는 remedy는 아니다.
- 같은 tool call 반복을 막는 loop 탐지 임계값은 `TOOL_CALL_LOOP_THRESHOLD = 5`다(`packages/core/src/services/loopDetectionService.ts#L29`).

### (4) list_changed와 description 표시

- list_changed:
  - `ToolListChangedNotificationSchema` handler가 `refreshTools()`를 부른다(`mcp-client.ts#L406-L424`, `#L696` 이후).
  - 서버가 `listChanged`를 선언하지 않아도 "Listening anyway for robustness…"라며 구독한다.
- 실행 확인:
  - `getConfirmationDetails`가 'Confirm MCP Tool Execution'에 `toolDescription`과 `toolParameterSchema`를 담는다(`mcp-tool.ts#L346-L383`).
  - UI는 접힌 "MCP tool details"에 `Description:`을 보여 주고, 키를 눌러야 펼쳐진다(`packages/cli/src/ui/components/messages/ToolConfirmationMessage.tsx#L180-L236`, `#L927-L959`).
  - trusted folder에서 서버가 `trust: true`이거나 allowlist(ProceedAlways)에 있으면 확인을 건너뛴다(`mcp-tool.ts#L352-L361`).
  - YOLO와 policy engine 기본값은 UNVERIFIED.

### (5) 조건 대응

| 조건 | 대응 |
|---|---|
| E_json_flag-like | **해당 (기본).** raw `CallToolResult` JSON에 `"isError":true`가 보인다. 클라이언트 설명문이 앞에 붙는다. |
| native is_error | **부분 해당.** 별도 플래그는 없고 Gemini 규약의 `response.error` 키를 쓴다. |
| E_unknown-like | 해당 없음. 평문만 가는 경로는 없다. |
| X_exception-like | 해당. 다만 같은 wrapper 안에 `{"error":{"message":"MCP error -32001: …","isError":true}}`로 들어간다. |
| remedy-added | 해당 없음. |
| reference-chatbot-like | 해당 없음. |

---

## 3. OpenAI Codex CLI (rust-v0.162.1) [CODE]

### (1) `isError=true`일 때 모델이 받는 것

- 경로는 다음과 같다.
  1. `handle_mcp_tool_call`(`CDX core/src/mcp_tool_call.rs#L130`)
  2. `McpHandler::handle_call`이 `McpToolOutput`을 만든다(`CDX core/src/tools/handlers/mcp.rs#L196-L275`).
  3. `to_response_item`이 `ResponseInputItem::FunctionCallOutput`을 만든다(`CDX core/src/tools/context.rs#L157-L162`).
- `response_payload`(`context.rs#L185-L215`)의 처리:
  - `CallToolResult::as_function_call_output_payload`(`CDX protocol/src/models.rs#L2304-L2340`)로 MCP `content`를 `input_text` item으로 바꾼다.
  - 그 앞에 `format!("Wall time: {wall_time_seconds:.4} seconds\nOutput:")` item을 넣는다.
- `success: Some(false)`는 내부 값이라 wire로 나가지 않는다.
  - 주석: "`success` remains internal metadata for downstream handling."(`models.rs#L2177-L2185`)
  - `Serialize`는 body만 직렬화한다(`models.rs#L2255-L2266`).
- `structuredContent`가 null이 아니면 그것만 JSON 문자열로 보내고 `content`는 버린다(`models.rs#L2316-L2335`).
- `codex-rs`에는 Chat Completions 경로가 없다(`chat/completions`, `"role": "tool"`을 grep해 0건). 따라서 모든 모델이 Responses API 형식을 받는다.
- 모델이 보는 형태 [DERIVED]:
  ```json
  {"type":"function_call_output","call_id":"call_…","output":[
    {"type":"input_text","text":"Wall time: 0.0021 seconds\nOutput:"},
    {"type":"input_text","text":"Error: tool execution failed"}]}
  ```
- 판단: 오류 텍스트가 그대로 전달된다. **isError 플래그는 사라진다.** 지시나 remedy는 없다. 클라이언트가 붙이는 것은 중립 헤더 "Wall time … Output:"뿐이다.

### (2) 예외

- 실행 경로의 오류는 `.map_err(|error| format!("tool call error: {error:?}"))`(`mcp_tool_call.rs#L550`)를 거친다.
- 그다음 `CallToolResult::from_result` → `from_error_text`(`models.rs#L2281-L2298`)가 text content와 `is_error: Some(true)`를 만든다. 직렬화는 (1)과 같아서 플래그는 역시 사라진다.
- 안쪽 오류 문구(`CDX codex-mcp/src/binding.rs#L303-L360`):
  - `"timed out awaiting tools/call after {timeout:.0?}"`
  - context `"tool call failed for `{server}/{tool_name}`"`
  - `"tool call rejected because the catalog changed after `{server}/{tool}` was prepared"`
- 기본 tool timeout은 `DEFAULT_TOOL_TIMEOUT = 300s`다(`codex-mcp/src/rmcp_client.rs#L107`, `connection_manager.rs#L363-L367`).
- [DERIVED] 모델이 보는 텍스트(anyhow `{:?}` 형식):
  ```
  Wall time: …\nOutput:
  tool call error: tool call failed for `srv/tool`

  Caused by:
      timed out awaiting tools/call after 300s
  ```
  - 여러 줄로 나뉘는 정확한 모양은 UNVERIFIED다.
  - JSON-RPC 오류 응답(-32602 등)을 rmcp가 어떻게 표시하는지도 UNVERIFIED다.
- 그 밖의 문구:
  - 인자 JSON parse 실패: `err: {e}`(`#L156`)
  - 도구를 쓸 수 없음: ``MCP tool `{server}/{tool}` is not available to the model``(`#L178`)

### (3) 재시도와 loop

- `call_with_preparation`에 재시도가 없다(`binding.rs#L303-L360`).
- 오류 출력은 다른 tool 출력과 똑같이 function_call_output으로 모델에게 돌아가고 turn이 이어진다.
- UNVERIFIED: turn loop에 오류 전용 중단 조건이 있는지 전부 확인하지는 않았다.
- system prompt(`models-manager/prompt.md`, `core/gpt_5_2_prompt.md`)에는 "오류가 나면 다시 시도하라" 같은 일반 지시가 없다(grep).

### (4) list_changed와 description 표시

- `on_tool_list_changed`는 `info!("MCP server tool list changed")`로 로그만 남긴다(`CDX rmcp-client/src/logging_client_handler.rs#L86-L88`). 알림을 받아도 refresh하지 않는다.
- 승인 정책:
  - 기본값은 `AppToolApproval::Auto`다(`config/src/mcp_types.rs#L26-L34`).
  - `requires_mcp_tool_approval`(`mcp_tool_call.rs#L2461-L2478`) 규칙: `readOnlyHint=true`면 승인 없음, `destructiveHint=true`면 승인, 나머지는 기본적으로 승인을 요구한다.
- 승인 질문은 `Allow the {server} MCP server to run tool "{tool}"?`다(`#L1956-L1972`).
- tool description의 행방:
  - elicitation `_meta`의 `tool_description`에 들어간다(`#L2045-L2050`).
  - Guardian(자동 검토) action에도 들어간다(`#L1541-L1553`).
  - TUI(`tui/src`)에는 `tool_description`을 그리는 코드가 없다(grep 0건). **사용자에게 description이 보이는지는 UNVERIFIED다.**
  - `approval_policy`(예: exec의 never)와 어떻게 얽히는지도 UNVERIFIED다.

### (5) 조건 대응

| 조건 | 대응 |
|---|---|
| E_unknown-like | **해당 (기본).** 평문이 그대로 가고 플래그는 없다. 중립 헤더 "Wall time…Output:"가 붙는다. |
| E_json_flag-like | 해당 없음. |
| native is_error | 해당 없음(wire에 필드 없음). |
| X_exception-like | **해당.** `tool call error: …` 접두어와 Rust error chain이 들어간다. |
| remedy-added | 해당 없음. |
| reference-chatbot-like | 해당 없음. |

---

## 4. fast-agent (v0.10.43) [CODE]

### (1) `isError=true`일 때 모델이 받는 것

- aggregator `call_tool`은 서버의 `CallToolResult`를 그대로 돌려준다(`FA src/fast_agent/mcp/mcp_aggregator.py#L2900-L2924`). 변환은 provider converter가 한다.
- Anthropic:
  - `BetaToolResultBlockParam(type="tool_result", content=…, is_error=result.is_error)`로 보낸다(`FA src/fast_agent/llm/provider/anthropic/multipart_converter_anthropic.py#L785-L850`).
  - 내용이 비면 `[No content in tool result]`가 들어간다. **native is_error다.**
- OpenAI Chat Completions:
  - `generic`이나 OpenAI 호환 endpoint(vLLM 등)도 이 경로를 쓴다. `GenericLLM(OpenAILLM)`(`llm_generic.py#L13`).
  - `role:"tool"`, `content=<text 그대로>`이고 플래그는 없다(`FA src/fast_agent/llm/provider/openai/multipart_converter_openai.py#L563-L633`).
  - **특이점:** content가 비면 `is_error`라도 `"[Tool completed successfully]"`로 채운다(`#L594-L598`, `#L626-L627`). 오류가 성공처럼 보인다.
- OpenAI Responses: `{"type":"function_call_output","call_id":…,"output":…}`이고 플래그는 없다(`FA src/fast_agent/llm/provider/openai/responses_content.py#L515-L548`).
- Google: `{"error": output_text or "Tool execution failed."}`, 성공이면 `{"result": …}`다(`FA src/fast_agent/llm/provider/google/google_converter.py#L288-L293`).
- Bedrock: `"status": "error"`(`multipart_converter_bedrock.py#L49`, `#L77`).
- 모든 provider에 공통으로, `structuredContent`가 있으면 text block 대신 그 JSON을 쓴다(`FA src/fast_agent/mcp/helpers/content_helpers.py#L142-L181`).
- 클라이언트가 붙이는 지시나 remedy는 없다.

### (2) 예외

- `_execute_on_server` → `_handle_session_method_error`가 다음 문자열을 `CallToolResult(is_error=True)`로 만든다. 이후 처리는 provider별로 (1)과 같다.
  ```
  f"Failed to {method_name} '{operation_name}' on server '{server_name}': {exc}"
  ```
  - 예: `Failed to call_tool 'read_file' on server 'fs': <exc>`(`mcp_aggregator.py#L2449-L2465`)
- Python MCP SDK의 timeout 문구는 mcp 1.20.0 기준으로 확인했다: "Timed out while waiting for response to {request.__class__.__name__}. Waited {timeout} seconds."(`modelcontextprotocol/python-sdk` tag `v1.20.0`, `src/mcp/shared/session.py#L276-L281`). fast-agent는 `mcp==2.3.0`에 고정돼 있어(`pyproject.toml#L18`) **2.3.0의 문구는 UNVERIFIED**다.
- 연결 오류:
  - `call_tool`은 replay 안전 목록 `_CONNECTION_ERROR_REPLAY_SAFE_METHODS`에 없다(`#L105-L117`). 그래서 다음 작업을 위해 재연결만 하고 오류 결과를 돌려준다(`#L2358-L2368`).
- 세션 종료(`_handle_session_terminated`, `#L2738-L2795`):
  - 재연결이 꺼져 있으면: `MCP server {s} session terminated - reconnection not enabled`
  - 재연결 뒤에도 실패하면: `MCP server {s} session terminated even after reconnection. The server may be persistently rejecting this session. Please check server status or try again later.` ← **클라이언트가 직접 쓴 remedy 비슷한 문구는 조사 범위에서 이것 하나다.**
- aggregator 밖으로 나온 예외는 `McpAgent`가 `Error: {e!s}`로 감싼다(`FA src/fast_agent/agents/mcp_agent.py#L2147-L2152`, `#L2210-L2215`).
- `run_tools`나 hook 자체가 예외를 내면 다음이 일어난다(`FA src/fast_agent/agents/tool_runner.py#L588-L603`, `#L625-L633`, `#L898-L905`).
  - `Tool hook or execution failed during {phase}: {exc}`가 만들어진다.
  - `FAST_AGENT_ERROR_CHANNEL`이 붙는다.
  - **loop가 멈춘다.**

### (3) 재시도와 loop

- `ServerSessionTerminatedError`가 나고 `reconnect_on_disconnect=true`면, 재연결한 뒤 같은 작업을 한 번 replay한다(`#L2738-L2795`). 설정에 따라 `tools/call`이 자동으로 다시 실행되는 경로다.
- OAuth challenge가 오면 재시도한다(`#L2382-L2389`).
- `is_error` 결과가 나와도 loop는 계속된다.
  - `max_iterations` 기본값은 `DEFAULT_MAX_ITERATIONS = 9999`다(`FA src/fast_agent/constants.py#L63`, `llm/request_params.py#L88`).
  - 한도에 닿으면 강제 요약 없이 멈춘다(`tool_runner.py#L862-L880`).

### (4) list_changed와 description 표시

- list_changed: `ToolListChangedNotification`을 받으면 `_handle_tool_list_changed` → `_refresh_server_tools`가 돈다(`FA src/fast_agent/mcp/client_callback_runtime.py#L256-L270`, `mcp_aggregator.py#L3509-L3525`).
- 승인:
  - 기본 handler는 `NoOpToolPermissionHandler`라서 승인 절차가 없다(`src/fast_agent/mcp/tool_permission_handler.py#L72`, `mcp_aggregator.py#L495-L500`).
  - ACP 모드에서는 ACP 클라이언트에 승인을 넘긴다. description을 보여 주는지는 UNVERIFIED다.

### (5) 조건 대응

| 조건 | 대응 |
|---|---|
| E_unknown-like | **해당.** OpenAI Chat·Responses. 우리 Qwen3/GPT-OSS + vLLM 구성이 여기에 해당한다. |
| native is_error | **해당.** Anthropic. Google은 `error` 키, Bedrock은 `status`. |
| E_json_flag-like | 해당 없음. |
| X_exception-like | 해당. `Failed to call_tool '…' on server '…': <exc>`가 오류 결과로 간다. |
| remedy-added | 세션 종료 후 재연결 실패라는 특수 경로에서만 해당. |
| reference-chatbot-like | 해당 없음. |

---

## 5. mcp-agent (main f62d849, v0.2.6) [CODE]

### (1) `isError=true`일 때 모델이 받는 것

- `AugmentedLLM.call_tool`은 `CallToolResult`를 그대로 돌려준다(`MA src/mcp_agent/workflows/llm/augmented_llm.py#L571-L650`).
- OpenAI(Ollama·LM Studio 하위 클래스도 같음):
  - `ChatCompletionToolMessageParam(role="tool", content=[mcp_content_to_openai_content_part(c) for c in result.content])`로 보낸다(`MA src/mcp_agent/workflows/llm/augmented_llm_openai.py#L605-L654`). **플래그는 없다.**
  - `OllamaAugmentedLLM(OpenAIAugmentedLLM)`, `LMStudioAugmentedLLM(OpenAIAugmentedLLM)` 상속 관계는 확인했다. Azure는 별도 converter라 UNVERIFIED다.
- Anthropic:
  - `ToolResultBlockParam(type="tool_result", content=…, is_error=result.isError)`로 보낸다(`MA src/mcp_agent/workflows/llm/augmented_llm_anthropic.py#L1252-L1282`). **native is_error다.**
  - **특이점:** text·image content가 하나도 없으면 `"No result returned"`를 넣고 `isError=True`로 강제한다. 빈 성공 결과가 오류로 바뀐다.
- Google:
  - `{"error": str(result.content)}`를 보낸다(`MA src/mcp_agent/workflows/llm/augmented_llm_google.py#L526-L540`).
  - TextContent 객체 list의 **Python repr**가 그대로 들어간다(예: `[TextContent(type='text', text='Error: tool execution failed', annotations=None, meta=None)]`). 정확한 repr 필드는 UNVERIFIED다.
- Bedrock: `"status": "error"`(`multipart_converter_bedrock.py#L243`, `#L264`; `augmented_llm_bedrock.py#L247`).
- 지시나 remedy는 없다.

### (2) 예외

- aggregator: `Failed to call tool '{local_tool_name}' on server '{server_name}': {str(e)}`가 `isError=True`로 간다(`MA src/mcp_agent/mcp/mcp_aggregator.py#L894-L912`).
- 바깥쪽: `Error executing tool '{name}': {str(e)}`(`augmented_llm.py#L638-L648`)
- `pre_tool_call`이 거부하면: `Error: Tool '{name}' was not allowed to run.`(`#L603-L612`)
- OpenAI 인자 JSON 오류: `Invalid JSON provided in tool call arguments for '{tool}'. Failed to load JSON: {e}`(`augmented_llm_openai.py#L629-L637`)
- SDK timeout은 `mcp>=1.20.0`(`pyproject.toml#L21`)이다. [DERIVED] 결과 문구는 `Failed to call tool 'X' on server 'Y': Timed out while waiting for response to ClientRequest. Waited N seconds.`다. 클래스 이름 부분은 UNVERIFIED다.
- OpenAI loop에서 `execute_many` 결과가 예외 객체이면, `Warning: Unexpected error during tool execution… Continuing...`를 로그에 남기고 tool 메시지를 **붙이지 않는다**(`augmented_llm_openai.py#L370-L380`). 그러면 다음 요청에 답이 없는 tool_call이 남는다. 그 뒤 API가 어떻게 반응하는지는 UNVERIFIED다.

### (3) 재시도와 loop

- 자동 재시도가 없다.
- OpenAI 경로는 `for i in range(params.max_iterations)`(기본 10, `augmented_llm_openai.py#L159`, `#L261`)를 돌며, `finish_reason == "tool_calls"`인 동안 계속된다(`#L358-L404`).
- **Anthropic·Bedrock 경로의 강제 최종 답:**
  - 조건: 마지막 iteration이고 직전 `stop_reason`이 `tool_use`일 때.
  - 이때 넣는 user 메시지: "We've reached the maximum number of iterations. Please stop using tools now and provide your final comprehensive answer based on all tool results so far. At the beginning of your response, clearly indicate that your answer may be incomplete…"
  - 위치: `augmented_llm_anthropic.py#L236-L249`, streaming 경로 `#L481-L495`, `augmented_llm_bedrock.py#L343-L362`
  - 이 요청에도 `tools`가 그대로 들어간다(`#L251-L257`). 모델이 여기서도 도구를 부를 수 있는지는 UNVERIFIED다.
- OpenAI와 Google 경로에는 이런 주입이 없다.

### (4) list_changed와 description 표시

- 클라이언트 쪽 list_changed handler가 `src/mcp_agent`에 없다. grep에 걸린 것은 서버 쪽 `send_*_list_changed`(예제와 temporal proxy)뿐이다.
- tool 목록은 `load_servers`에서 cache되고 `force` 없이는 다시 불러오지 않는다(`mcp_aggregator.py#L451-L470`, `#L636` 이후). Anthropic 경로의 `update_tools()`(`#L437-L450`, `#L701`)도 cache를 읽는 것으로 보이지만 UNVERIFIED다.
- 승인 절차는 기본으로 없다. `pre_tool_call` hook이 거부할 수만 있다.

### (5) 조건 대응

| 조건 | 대응 |
|---|---|
| E_unknown-like | **해당.** OpenAI 호환(우리 구성). |
| native is_error | **해당.** Anthropic. Google은 `error` 키 안에 Python repr, Bedrock은 `status`. |
| E_json_flag-like | 엄밀히는 해당 없음. Google의 repr가 구조화 텍스트에 가깝다. |
| X_exception-like | 해당. `Failed to call tool '…' on server '…': …` |
| remedy-added | 해당 없음. |
| reference-chatbot-like | **부분 해당.** Anthropic·Bedrock에서 `max_iterations`를 작게(예: 2) 잡으면 "도구 1라운드 → 강제 최종 답 요청"이 된다. 기본값(10)에서는 해당하지 않는다. |

---

## 6. Claude Code — 비공개 소스, 공식 문서만 근거 [DOCS]

### (1) `isError=true`일 때 모델이 받는 것

- `code.claude.com/docs/en/mcp` "MCP output limits and warnings": "**Error results**: when a tool returns a result marked `isError: true`, Claude receives the result's text as the tool's error message. Error text longer than about 11,000 characters keeps only its first 5,000 and last 5,000 characters, with a marker between them that says how many characters were removed".
- `code.claude.com/docs/en/hooks`, PostToolUseFailure:
  - "Runs when a tool that started executing fails: the tool threw an error, or an MCP tool returned an error result. Use this to log failures, send alerts, or provide corrective feedback to Claude."
  - "The `error` string is generally the same text Claude receives as the failed tool's result."
- 입력 검증 단계에서 거부되면 "returned as `tool_use_error` results"로 돌아간다.
- API 수준의 처리는 **UNVERIFIED**다. 구체적으로 Anthropic `tool_result.is_error=true`를 설정하는지, 텍스트에 wrapper tag를 붙이는지 모른다. "as the tool's error message"라는 표현이 native 채널을 쓴다는 뜻으로 읽히지만 문서가 명시하지는 않는다.
- 기본 상태에서 클라이언트가 붙이는 remedy는 문서에 없다.
- 다만 PostToolUseFailure hook의 `additionalContext`("String added to Claude's context alongside the error")로 운영자가 remedy를 붙일 수 있다.

### (2) 예외

- PostToolUseFailure의 `is_interrupt` 필드: "True when the failure reached Claude Code as an abort rather than as an error the tool reported".
- timeout 관련 문서 내용:
  - per-server `timeout`과 `MCP_TOOL_TIMEOUT`이 있고, 설정하지 않으면 "about 28 hours"다.
  - idle timeout은 HTTP 5분, stdio 30분이다. "aborts with an error instead of waiting for the wall-clock limit."
- 세션을 이어 연 뒤 서버가 아직 연결되지 않았으면 `No such tool available` tool error가 난다.
- 예외일 때 모델이 받는 정확한 텍스트는 UNVERIFIED다.

### (3) 재시도와 loop

- 자동 재시도는 연결과 인증 쪽에만 문서화돼 있다.
  - 원격 서버 reconnect.
  - OAuth 401: "refreshes the stored token, reconnects, and retries the request once".
  - `headersHelper`가 있을 때 401/403: "retries the call once".
- `isError` 결과에 대해 클라이언트가 자동으로 다시 실행한다는 내용은 없다.
- loop가 이어진다는 점은 hook의 "provide corrective feedback to Claude"에서 미루어 알 수 있다. 정확한 동작은 UNVERIFIED다.

### (4) list_changed와 description 표시

- list_changed: "**In an interactive terminal session**, Claude Code fetches the updated list from that server…" / "-p … refreshes only the tool list on these notifications."
- 승인:
  - MCP tool 승인 prompt가 있다(permissions 문서의 "including Bash, PowerShell, file, and MCP tool prompts").
  - project scope의 `.mcp.json` 서버는 연결 전에 승인을 받는다.
  - `_meta["anthropic/requiresUserInteraction"]`가 붙은 도구는 매번 확인한다.
  - **승인 prompt가 tool description을 보여 주는지는 UNVERIFIED**(문서에 언급 없음).
- **poisoning과 관련된 문서 사항:**
  - "Claude Code truncates each tool description and each server's instructions at 2,048 characters by default."
  - tool search가 기본으로 켜져 있다: "Only tool names and server instructions load at session start". 즉 오염된 description은 ToolSearch로 해당 도구를 불러온 뒤에야 context에 들어간다.

### (5) 조건 대응

| 조건 | 대응 |
|---|---|
| native is_error | 가능성이 높으나 UNVERIFIED. 텍스트가 그대로 간다는 것만 문서로 확인됨. |
| remedy-added | 기본값은 아님. hook `additionalContext`를 쓰면 해당. |
| 그 밖의 조건 | UNVERIFIED. |

---

## 7. Claude Desktop — 비공개 소스, 공식 문서만 근거 [DOCS]

- 출처: `modelcontextprotocol.io/docs/develop/connect-local-servers`(MCP 공식 문서의 Claude Desktop 안내).
  - "All actions require your explicit approval before execution" / "Before executing any file system operation, Claude will request your approval."
  - 문제 해결 항목 "Tool calls failing silently": "If Claude attempts to use the tools but they fail: 1. Check Claude's logs for errors…"
- `support.claude.com`의 로컬 MCP 안내 문서(10949351)에는 승인 화면, 오류 표시 방식, timeout 내용이 없다.
- (1)~(5) 전부 **UNVERIFIED**다. 모델에 전달되는 오류 형식, 예외 문구, 재시도, list_changed, 승인 시 description 표시 여부를 확인하지 못했다. Anthropic API를 쓰므로 native is_error 경로를 쓸 가능성은 있으나 확인하지 않았다.

## 8. Cursor — 비공개 소스, 공식 문서만 근거 [DOCS]

- 출처: `cursor.com/docs/context/mcp`.
  - "Cursor asks for approval before using MCP tools by default. Click the arrow next to the tool name to see arguments."
  - "Cursor shows the response in chat with expandable views of arguments and responses".
  - FAQ "What happens if an MCP server crashes or times out?": "Cursor shows an error message in chat / The tool call is marked as failed / You can retry the operation or check logs for details / Other MCP servers continue working normally".
- 문서가 다루지 않는 것은 **UNVERIFIED**다: 모델에 전달되는 텍스트, `isError` 전달 방식, 자동 재시도, list_changed, 승인 화면의 description 표시.
- 문서의 "retry"는 사용자가 하는 재시도로 읽힌다.

---

## 9. 종합 대응표

기호: ● 기본 동작이 해당 / ◐ 일부 경로나 설정에 따라 해당 / ✕ 해당 없음 / ? UNVERIFIED

| 클라이언트 (모델 API) | E_unknown-like | E_json_flag-like | native is_error | X_exception-like | remedy-added | reference-chatbot-like | 오류 뒤 loop | 자동 재실행 | list_changed refresh | 승인 시 description 표시 |
|---|---|---|---|---|---|---|---|---|---|---|
| Gemini CLI (Gemini) | ✕ | ● (클라이언트 설명문 포함) | ◐ (`error` 키) | ● (같은 wrapper) | ✕ | ✕ | 계속 | ✕ | ● | ● (접힘) |
| Codex (Responses) | ● (+Wall time 헤더) | ✕ | ✕ | ● (`tool call error:`) | ✕ | ✕ | 계속 | ✕ | ✕ (로그만) | ? |
| fast-agent (OpenAI 호환) | ● | ✕ | ✕ | ● | ◐ (세션 종료 경로) | ✕ | 계속 (hook 예외 때 중단) | ◐ (reconnect replay) | ● | 기본 승인 없음 |
| fast-agent (Anthropic) | ✕ | ✕ | ● | ● | ◐ | ✕ | 계속 | ◐ | ● | 기본 승인 없음 |
| mcp-agent (OpenAI 호환) | ● | ✕ | ✕ | ● | ✕ | ✕ | 계속 (≤10) | ✕ | ✕ | 기본 승인 없음 |
| mcp-agent (Anthropic/Bedrock) | ✕ | ✕ | ● | ● | ✕ | ◐ (마지막 iteration 강제 답) | 계속 (≤10) | ✕ | ✕ | 기본 승인 없음 |
| Claude Code | ? | ? | ? (가능성 높음) | ? | ◐ (hook) | ✕? | 계속? | 인증 경우만 | ● | ? |
| Claude Desktop | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? |
| Cursor | ? | ? | ? | ? | ? | ? | ? | ? | ? | ? (인자는 표시) |

## 10. 논문과 실험 설계에 주는 함의

1. **"지시 없는 오류"가 실제 기본값이다.** 오픈소스 4종 모두 서버 오류 텍스트를 그대로 넘기고 해결책을 덧붙이지 않는다.
   - E_unknown과 비슷한 평문: Codex, fast-agent·mcp-agent의 OpenAI 경로.
   - E_json_flag와 비슷한 raw JSON: Gemini CLI.
   - 두 조건 모두 실제 배포에 근거가 있다.
2. **native is_error 조건은 Anthropic(그리고 Bedrock·Gemini의 고유 필드) 경로에서만 실재한다.**
   - Qwen3·GPT-OSS를 OpenAI 호환 endpoint로 쓰는 실제 클라이언트에서는 플래그가 wire에서 사라진다.
   - chat template(Qwen3 `<tool_response>`, harmony)이 오류 플래그를 표현할 수 있는지는 이번 조사에서 확인하지 않았다(UNVERIFIED).
   - 이 조건은 "provider-native 채널이 있다면"을 가정한 반사실(counterfactual) 조건으로 소개하는 편이 정확하다.
3. **remedy-added는 클라이언트 기본값이 아니다.** 다음 세 경로로 들어온다. 따라서 "remedy가 일부 모델에서 억제한다"는 결과는 서버·운영자 쪽 완화책으로 해석하는 것이 맞다.
   - 서버 작성자가 Anthropic의 "Write instructive error messages … Retry after 60 seconds" 권고를 따르는 경우.
   - Claude Code PostToolUseFailure hook의 `additionalContext`.
   - fast-agent의 세션 종료 문구라는 특수한 경로.
4. **reference-chatbot-like는 조사한 agentic 클라이언트의 기본값이 아니다.**
   - 코드로 존재하는 유사 사례는 mcp-agent의 마지막 iteration 강제 답 하나다.
   - 이 형식이 억제 효과를 보인다면 "loop를 일찍 닫는 클라이언트 설계"의 효과로 표현하고, 기본 배포에는 해당하지 않는다고 함께 밝혀야 한다.
5. **명세가 오류를 self-correct·retry 채널로 정의한다(MCP 2025-11-25 tools.mdx).** 모든 클라이언트가 loop를 유지한 채 다시 시도할지를 모델에게 맡긴다. 오류 재활성화 취약점은 특정 클라이언트의 버그가 아니라 명세가 권장하는 설계에서 생긴다고 서술할 수 있다.
6. **Claude Code에는 공격 표면을 줄이는 기본값이 두 가지 있다.** 일반화할 때 이 점을 밝혀야 한다.
   - description을 2,048자에서 자른다.
   - tool search로 description 로딩을 미룬다.
7. **확인이 필요한 항목**
   - Claude Code와 Claude Desktop이 `is_error`를 실제로 어떻게 직렬화하는지(필요하면 승인된 범위에서 proxy를 둬 관찰).
   - fast-agent의 `mcp==2.3.0` timeout 문구.
   - Codex anyhow 오류의 정확한 줄 구성.
   - Cursor 전반.
