# 실제 MCP 클라이언트가 실패한 도구 호출을 모델에 넘기는 방식 (SDK·프레임워크)

- 작성: 2026-10-10
- 방법: 공개 소스를 고정 commit에서 raw 파일로 읽었다. 클라이언트는 실행하지 않았다. 모델 호출은 하지 않았다.
- 예외 하나: Python SDK v2의 `str(CallToolResult)` 문자열은 로컬 pydantic 2.12.4로 재구성했다. 필드 선언을 최소한으로 옮겨 적은 사본이며, 실제 패키지를 실행한 결과는 아니다.
- 확인하지 못한 항목은 **UNVERIFIED**로 표시했다.
- 인용한 문자열은 모두 원문 그대로이며 영어다.

## 0. 고정한 버전

| 대상 | repo | commit (날짜) | 비고 |
|---|---|---|---|
| MCP Python SDK | modelcontextprotocol/python-sdk | `91941ed` (2026-10-05) | 최신 릴리스 v2.3.0. 비교용으로 v1.30.0·v1.26.0도 읽음 |
| MCP TypeScript SDK | modelcontextprotocol/typescript-sdk | `b022522` (2026-10-05) | 최신 릴리스 v2.3.1. 비교용으로 v1.25.0도 읽음 |
| MCP 공식 문서 | modelcontextprotocol/modelcontextprotocol | `c518f7a` (2026-10-08) | build-client 튜토리얼, spec tools |
| OpenAI Agents SDK (Python) | openai/openai-agents-python | `125efa0` (2026-10-08) | 최신 릴리스 v0.23.1. v0.2.3–v0.22.0도 비교 |
| langchain-mcp-adapters | langchain-ai/langchain-mcp-adapters | `52a4535` (2026-09-11) | pyproject 버전 0.3.2. 0.1.x–0.2.2와 비교 |
| LangGraph ToolNode | langchain-ai/langgraph | `b4991f1` | `prebuilt==1.0.0/1.0.1/1.0.2`와 비교 |
| LangChain core·provider·create_agent | langchain-ai/langchain | `b060a74` | |
| LlamaIndex MCP tools | run-llama/llama_index | `6dd2f3c` (2026-10-08) | `llama-index-tools-mcp` 0.6.0, `mcp>=2.0.0,<3` |
| Pydantic AI | pydantic/pydantic-ai | `69ea1e5` (2026-10-10) | 최신 릴리스 v2.55.0. v0.2.10–v1.107.1과 비교 |

URL 접두어:

- PY = `https://github.com/modelcontextprotocol/python-sdk/blob/91941ed4d3985d59def99e090baa3f880c626cc8/`
- TS = `https://github.com/modelcontextprotocol/typescript-sdk/blob/b022522089a0c8b632595c6e7b536453945ed5a9/`
- DOCS = `https://github.com/modelcontextprotocol/modelcontextprotocol/blob/c518f7a927cff918bce35d3522fcdb046d264d7c/`
- OAI = `https://github.com/openai/openai-agents-python/blob/125efa029b4bfd84238bd2c4fd69c3406f802663/`
- LCA = `https://github.com/langchain-ai/langchain-mcp-adapters/blob/52a4535f3eb4b98f386836e4d9b8c4cadf99afca/`
- LG = `https://github.com/langchain-ai/langgraph/blob/b4991f1ba36a2449ab59c38ab71828ee865bff84/`
- LC = `https://github.com/langchain-ai/langchain/blob/b060a7466482ed5dac5fa1ef12e3ad21cccce385/`
- LI = `https://github.com/run-llama/llama_index/blob/6dd2f3cdd9ce7ff927ea8d46ccee08875bb00f95/`
- PAI = `https://github.com/pydantic/pydantic-ai/blob/69ea1e57201ed59e7d30fbe4a7590d193acecce0/`

## 1. 요약표

`isError=true`이고 content가 `"Error: tool execution failed"` 한 블록일 때 모델이 받는 메시지와, 예외가 났을 때 받는 메시지를 정리했다.

| 클라이언트 (기본 설정) | isError일 때 모델이 받는 것 | 네이티브 플래그 | 클라이언트가 덧붙이는 문구 | 예외일 때 모델이 받는 것 | 자동 재시도 | 루프 |
|---|---|---|---|---|---|---|
| Python SDK `ClientSession.call_tool` | (LLM 연결 없음) `CallToolResult(is_error=True)`를 그대로 반환 | – | 없음 | `MCPError`를 raise. `str(e)`는 message 본문 | 없음 | – |
| Python SDK `simple-chatbot` 예제 | system 메시지 `Tool execution result: meta=None content=[TextContent(type='text', text='Error: tool execution failed', annotations=None, meta=None)] structured_content=None is_error=True result_type='complete'` (v2). v1.x는 `structuredContent=None isError=True` | 없음. repr 문자열 안에 `is_error=True`가 들어 있음 | 없음. 다만 system prompt에 "Transform the raw data into a natural, conversational response" 등 요약 지시가 있음 | system 메시지 `Error executing tool: <str(e)>`. 예: `Error executing tool: Request 'tools/call' timed out` | 예외만 2회 시도(1초 간격). isError는 재시도 안 함 | 1회 실행 뒤 최종 응답을 강제. 두 번째 응답은 도구 호출로 해석하지 않음 |
| TS SDK `Client.callTool` | (LLM 연결 없음) `result.isError`를 그대로 반환 | – | 없음 | `ProtocolError` 또는 `SdkError`를 throw. 예: `Request timed out` (v2), `MCP error -32001: Request timed out` (v1.x) | 없음 | – |
| TS `examples/client-quickstart` (Anthropic) | `tool_result{content:"Error: tool execution failed", is_error:true}` | Anthropic `is_error` | 없음 | 잡지 않음. 프로세스가 `exit(1)`로 끝남 | 없음 | 모델이 도구를 그만 부를 때까지 반복 |
| TS `examples/cli-client` (참조 host) | Anthropic: `is_error:true`. OpenAI: `"[tool error] Error: tool execution failed"`. Gemini: `functionResponse.response={content, isError:true}` | Anthropic만 | `[tool error] ` 접두어(OpenAI만). system prompt에 "report tool failures honestly" | `Tool call failed: <reason>`, isError=true. 예: `Tool call failed: Request timed out` | 없음 | 최대 8 round |
| MCP 공식 튜토리얼 Python 2026-07-28 | `tool_result{content:"<text>", is_error:result.is_error}` | Anthropic `is_error` | 없음 | 잡지 않음 | 없음 | 1 round 뒤 한 번 더 호출하고, 그 응답의 tool_use는 버림 |
| MCP 공식 튜토리얼 Python 2025-06-18 | `tool_result{content: result.content}`. isError는 전달 안 함 | 없음 | 없음 | 잡지 않음 | 없음 | 위와 같음 |
| OpenAI Agents SDK v0.23 | 텍스트 그대로. Responses: `function_call_output.output=[{"type":"input_text","text":"Error: tool execution failed"}]`. Chat Completions: `role:"tool", content:[{"type":"text","text":"..."}]` | 없음. isError를 버림 | 없음 | `An error occurred while running the tool. Please try again.` (원인 텍스트 없음) | `max_retry_attempts=0` | 기본 `max_turns=10`, `run_llm_again` |
| OpenAI Agents SDK v0.8–v0.22 | 위와 같음 | 없음 | 없음 | `An error occurred while running the tool. Please try again. Error: <str(e)>` | 0 | 위와 같음 |
| OpenAI Agents SDK v0.2.3–v0.7.0 | `TextContent`를 JSON으로 직렬화한 문자열 `{"type":"text","text":"...",...}`. isError 키는 없음 | 없음 | 없음 | `AgentsException` → run 전체 중단 | 없음 | 예외 시 중단 |
| langchain-mcp-adapters ≥0.3.0 | `ToolMessage(content=[{"type":"text","text":"Error: ..."}], status="error")` | ChatAnthropic이면 `is_error`. ChatOpenAI는 status를 버림 | 없음 | 잡지 않음. 아래 ToolNode 규칙을 따름 | 없음 | create_agent/ToolNode 루프 |
| langchain-mcp-adapters ≤0.2.2 | `ToolException("Error: ...")` raise → ToolNode가 처리 | – | ToolNode 설정에 따름 | 같음 | 없음 | – |
| LangGraph ToolNode `handle_tool_errors=True` (prebuilt ≤1.0.1의 기본값) | (adapter ≤0.2.2) `Error: ToolException('Error: tool execution failed')\n Please fix your mistakes.` | ChatAnthropic이면 `is_error` | `Please fix your mistakes.` | `Error: <repr(e)>\n Please fix your mistakes.` | 없음 | 계속 |
| LangGraph ToolNode 기본값 (prebuilt ≥1.0.2) | (adapter ≤0.2.2) ToolException을 다시 raise → graph 실행 중단 | – | – | 다시 raise → 중단 | 없음 | 중단 |
| LlamaIndex `McpToolSpec` + FunctionAgent/ReActAgent | `str(CallToolResult)` pydantic repr. simple-chatbot과 같은 v2 문자열이고 앞의 `Tool execution result: `만 없음 | 없음. repr 안에 `is_error=True` | 없음 | `str(e)` 그대로. 예: `Request 'tools/call' timed out` | 없음 | 최대 20 iteration |
| Pydantic AI v2.55 (`tool_error_behavior='retry'`) | `Error: tool execution failed\n\nFix the errors and try again.` (`RetryPromptPart`) | Anthropic이면 `is_error=True`. OpenAI는 `role:"tool"` 텍스트 | `Fix the errors and try again.` | `McpError`는 `<str(e)>\n\nFix the errors and try again.` 그 밖의 예외는 중단(UNVERIFIED) | 없음. 모델에게 재시도를 요청할 뿐. 같은 도구의 retry 예산은 1 | 같은 도구에서 두 번째 오류가 나면 `UnexpectedModelBehavior`로 중단 |

## 2. 클라이언트별 상세

### 2.1 MCP Python SDK (`ClientSession.call_tool`, `examples/clients/simple-chatbot`)

**(1) isError 결과**

- `ClientSession.call_tool`은 `CallToolResult`를 그대로 돌려준다. `is_error`가 참이면 output schema 검증만 건너뛴다(`if isinstance(result, types.CallToolResult) and not result.is_error: await self.validate_tool_result(...)`).
  - PY `src/mcp/client/session.py#L1052-L1116` (L1101-1102)
  - SDK 자체는 LLM 문맥을 만들지 않는다.
- v2의 `CallToolResult` 필드는 `content`, `structured_content`, `is_error`, `result_type`다. `MCPModel`은 `alias_generator=to_camel`을 쓴다.
  - PY `src/mcp-types/mcp_types/_types.py#L45-L48`, `#L1463-L1484`
- `simple-chatbot`:
  - 결과를 `return f"Tool execution result: {result}"`로 만든다. `result`는 `CallToolResult` 객체이므로 pydantic `__str__`가 적용된다.
    - PY `examples/clients/simple-chatbot/mcp_simple_chatbot/main.py#L318`
  - 이 문자열은 `messages.append({"role": "system", "content": result})`로 **system 역할**에 들어간다(L385-389).
  - v2 문자열(로컬 재구성):
    `Tool execution result: meta=None content=[TextContent(type='text', text='Error: tool execution failed', annotations=None, meta=None)] structured_content=None is_error=True result_type='complete'`
  - v1.x(v1.30.0까지)는 필드 이름이 camelCase다(`structuredContent`, `isError`). 그래서 문자열은 `... structuredContent=None isError=True`다. 본 연구 `src/cs_common.py`의 `sdk` 렌더가 이 v1.x 형식과 일치한다. v2와는 필드 이름이 다르고 `result_type='complete'`가 없다.
    - `https://github.com/modelcontextprotocol/python-sdk/blob/v1.30.0/src/mcp/types.py#L1363-L1369`
  - 클라이언트가 오류 문구를 덧붙이지는 않는다. 다만 system prompt가 결과 처리 방식을 지시한다: "After receiving a tool's response: 1. Transform the raw data into a natural, conversational response 2. Keep responses concise but informative ... 5. Avoid simply repeating the raw data" (L347-367).

**(2) 예외**

- `simple-chatbot`은 `error_msg = f"Error executing tool: {str(e)}"`를 만들고, 이것도 system 메시지로 넣는다(L319-322).
- v2의 `MCPError.__str__`는 `self.message`를 돌려준다.
  - PY `src/mcp/shared/exceptions.py#L51-L52`
- 대표 message:
  - timeout: `Request 'tools/call' timed out`. PY `src/mcp/shared/jsonrpc_dispatcher.py#L442`
  - 연결 종료: `Connection closed`. 같은 파일 L80, L340, L413
  - 그래서 v2 timeout이면 모델은 `Error executing tool: Request 'tools/call' timed out`를 받는다.
- 주의: `simple-chatbot`은 `ClientSession(read, write)`에 read timeout을 주지 않는다(L90). 기본 설정에서는 timeout 예외가 생기지 않을 수 있다(UNVERIFIED: v2 dispatcher의 기본 timeout 값).
- v1.x의 `McpError` timeout message는 `Timed out while waiting for response to ClientRequest. Waited {timeout} seconds.`다.
  - `https://github.com/modelcontextprotocol/python-sdk/blob/v1.26.0/src/mcp/shared/session.py#L296-L301`
  - `ClientRequest`라는 클래스 이름은 v1 `call_tool`의 호출 형태로 추정했다(UNVERIFIED).

**(3) 재시도와 루프**

- `ClientSession`은 재시도하지 않는다.
- `simple-chatbot`의 `execute_tool(retries=2, delay=1.0)`은 **예외만** 다시 시도한다. 총 2회 시도하고 그 사이 1초를 쉰다(L119-160). isError 결과는 첫 시도에서 바로 돌려준다.
- 루프는 사용자 입력 1회 → 모델 응답 → (JSON이면) 도구 1회 실행 → system 결과 → **최종 응답 1회**다. 최종 응답은 다시 파싱하지 않으므로 두 번째 도구 호출은 실행되지 않는다(L380-393).
- 도구 호출은 응답 전체가 `{"tool":..., "arguments":...}` JSON일 때만 인식한다(L300-327).

**(4) 도구 목록**

- system prompt의 도구 설명은 시작할 때 한 번 만든다(L340-367).
- 도구를 호출할 때마다 `list_tools()`를 다시 부르지만, 서버를 찾는 데만 쓴다(L306-308). system prompt는 갱신하지 않는다.
- 사용자 승인은 없다.
- SDK에는 opt-in 기능만 있다. 응답 캐시가 `ToolListChangedNotification`을 받으면 비우고(PY `src/mcp/client/caching.py#L325`), `Client.listen(tools_list_changed=True)`로 구독할 수 있다(PY `src/mcp/client/client.py#L696-L705`).

**참고: 서버 SDK가 원인 없는 오류를 만든다.** 공식 Python 서버(`MCPServer`)는 예상하지 못한 예외를 `is_error=True`와 `Error executing tool <name>`로 바꾼다. 예외 내용은 서버 로그에만 남긴다.

- PY `src/mcp/server/mcpserver/tools/base.py#L156-L161`, `#L207-L213`
- PY `src/mcp/server/mcpserver/server.py#L437-L456`
- 문서: PY `docs/servers/handling-errors.md` ("the model learns only that the call failed")
- v1.x FastMCP는 `Error executing tool {name}: {e}`처럼 예외 문자열을 포함했다(v1.30.0 `src/mcp/server/fastmcp/tools/base.py#L117`).
- 따라서 원인이 없는 오류(E_unknown 계열)는 실험용 가공물이 아니다. 공식 SDK 서버가 기본으로 만드는 출력이다.

**(5) 매핑**

| 경로 | 해당 조건 |
|---|---|
| `simple-chatbot` isError | reference-chatbot-like. 오류 표현은 E_unknown 텍스트를 Python repr의 `is_error=True` 안에 담은 형태다. 형식은 E_json_flag와 가깝지만 JSON은 아니고 content도 비어 있지 않다 |
| `simple-chatbot` 예외 | X_exception-like와 정확히 같은 틀(`Error executing tool: <msg>`)이다. 실제 message는 `Request 'tools/call' timed out`이다 |
| SDK 서버의 unexpected exception | E_unknown-like. `Error executing tool <name>`이고 원인이 없다 |

### 2.2 MCP TypeScript SDK (`Client.callTool`, 공식 예제 2종)

**(1) isError 결과**

- `Client.callTool`은 결과를 그대로 돌려준다. 문서 주석에 다음과 같이 적혀 있다: "Tool results have two error surfaces: `result.isError` for tool-level failures ..., and thrown ProtocolError ... or SdkError for SDK-level issues (timeouts, missing capabilities)."
  - TS `packages/client/src/client/client.ts#L2286-L2327`
- isError면 output schema 검증을 건너뛴다(L2450-2458).
- `examples/client-quickstart`(Anthropic):
  - text 블록을 `\n`으로 이어 `tool_result.content`에 넣는다.
  - `...(result.isError ? { is_error: true } : {})`로 네이티브 플래그를 붙인다.
  - TS `examples/client-quickstart/src/index.ts#L92-L114`
- `examples/cli-client`(README가 "the reference MCP host"라고 부름):
  - `host.executeToolCall`이 `{ parts: toolResultToParts(result), isError: result.isError === true }`를 만든다.
    - TS `examples/cli-client/host/host.ts#L181-L211`
  - content가 비어 있으면 `(tool returned no content)`로 대체한다(`host/content.ts#L66-L72`).
  - provider별 매핑:
    - Anthropic: `is_error: message.isError ?? false` (`providers/anthropic.ts#L33-L45`)
    - OpenAI: `content: message.isError ? `[tool error] ${text}` : text` (`providers/openai.ts#L13-L14`, `#L22-L28`)
    - Gemini: `response: { content, ...(message.isError ? { isError: true } : {}) }` (`providers/gemini.ts#L27-L33`)
  - system prompt에 "Use them when they help, report tool failures honestly, and keep answers short" 문구가 있다(`host/loop.ts#L12-L15`).

**(2) 예외**

- v2 timeout은 `SdkError(SdkErrorCode.RequestTimeout, 'Request timed out', { timeout })`다. 기본 timeout은 60초다.
  - TS `packages/core-internal/src/shared/protocol.ts#L103`, `#L1582-L1583`
- 연결 종료는 `Connection closed`다(L850).
- v2 `ProtocolError`는 message를 접두어 없이 쓴다(`packages/core-internal/src/types/errors.ts#L45-L53`).
- v1.x `McpError`는 `MCP error ${code}: ${message}` 형식이다.
  - `https://github.com/modelcontextprotocol/typescript-sdk/blob/v1.25.0/src/types.ts#L2263-L2269`
- `client-quickstart`는 `processQuery`에서 예외를 잡지 않는다. 그래서 `main`의 catch가 `process.exit(1)`로 끝낸다(index.ts L172-199).
- `cli-client`는 `Tool call failed: ${reason}`를 isError=true로 모델에 준다. 사용자가 취소하면 `Tool call cancelled by the user.`를 준다(host.ts L212-220). 주석은 다음과 같다: "A thrown ProtocolError/SdkError (unknown tool, timeout, lost connection) is not the same thing as a tool-level isError result, but the model should see both as failures."

**(3) 재시도와 루프**

- 자동 재시도는 없다.
  - 예외: `Client.callTool`에 `HEADER_MISMATCH` 때 목록을 다시 받고 재시도하는 경로가 있다(client.ts L1860 주석). 2026-07-28 header mirroring 전용이며 오류 결과와는 무관하다.
- `client-quickstart`는 tool_use가 없을 때까지 반복한다(L77-135).
- `cli-client`는 `MAX_TOOL_ROUNDS = 8`이다. isError 결과도 모델에 다시 보낸다. 주석: "`isError` results still go to the model — it is allowed to read the error and try something else." (loop.ts L9-10, L36-98)

**(4) 도구 목록**

- TS SDK는 `ClientOptions.listChanged` 핸들러로 `notifications/tools/list_changed`를 받으면 목록을 다시 가져올 수 있다(client.ts L287, L752-783).
- `cli-client`는 이 기능을 써서 도구 목록을 갱신한다(host.ts L336-367). 다만 한 사용자 turn 안에서는 목록을 고정한다(loop.ts L45-47).
- 승인 게이트는 없다. 주석: "cli-client executes tool calls without a confirmation gate because an interactive user watches every `→` line" (loop.ts L73-75).
- `/tools` 명령은 도구 설명을 사용자에게 보여 준다. 승인과는 무관하다(loop.ts L179-185).

**(5) 매핑**

| 경로 | 해당 조건 |
|---|---|
| quickstart, cli-client의 Anthropic provider | native is_error flag + 텍스트 원문 |
| cli-client의 OpenAI provider | E_unknown-like에 `[tool error] ` 표지가 붙은 형태 |
| cli-client의 Gemini provider | 구조화 객체 안의 `isError:true`. E_json_flag와 가깝지만 JSON 텍스트가 아니라 provider 필드다 |
| cli-client 예외 | X_exception-like (`Tool call failed: Request timed out`) |

### 2.3 MCP 공식 "Build an MCP client" 튜토리얼 (Python)

- 2026-07-28판:
  - `tool_result`에 텍스트를 이어 붙이고 `"is_error": result.is_error`를 넣는다.
  - 본문 설명: "A tool that raises does not raise here: it answers with `is_error` set, and passing that flag on lets Claude read the message and try something else."
  - DOCS `docs/docs/2026-07-28/develop/build-client.mdx#L174-L218`
- 2025-06-18판:
  - `"content": result.content`만 넣는다. isError는 전달하지 않는다.
  - DOCS `docs/docs/2025-06-18/develop/build-client.mdx#L195-L226`
- 두 판 모두 도구를 1 round 실행한 뒤 모델을 한 번 더 부른다. 그 응답에서는 text만 모으고 tool_use는 실행하지 않는다.
- 예외는 잡지 않는다. 재시도도 없다.
- 매핑:
  - 2026-07-28판: native is_error.
  - 2025-06-18판: E_unknown-like(플래그 없음).
  - 루프 구조는 reference-chatbot-like(single round)다. 단 요약 지시는 없다.
- spec 2026-07-28 tools는 "Clients **SHOULD** provide tool execution errors to language models to enable self-correction."라고 쓴다. 같은 문서에 "Prompt for user confirmation on sensitive operations"도 권고한다.
  - DOCS `docs/specification/2026-07-28/server/tools.mdx#L760-L796`

### 2.4 OpenAI Agents SDK (Python, MCP tool wrapper)

**(1) isError 결과**

- `MCPUtil.invoke_mcp_tool`은 isError 결과를 성공과 같은 경로로 처리한다.
  - `use_structured_content`가 켜져 있어도 오류 결과에서는 content를 쓴다. 코드는 `if server.use_structured_content and structured_content and not result_is_error(result)`다.
  - text 블록은 `ToolOutputTextDict(type="text", text=item.text)`가 된다. **isError 플래그는 모델로 전달되지 않는다.**
  - OAI `src/agents/mcp/util.py#L790-L821`
- 블록이 하나면 출력은 `[{"type":"input_text","text":"<원문>"}]`(Responses `function_call_output.output`)가 된다.
  - OAI `src/agents/items.py#L845-L925`, `#L1004-L1007`
- Chat Completions 모델이면 `{"role":"tool","tool_call_id":...,"content":[{"type":"text","text":"<원문>"}]}`가 된다.
  - OAI `src/agents/models/chatcmpl_converter.py#L869-L902`
- 오류 문구를 덧붙이지 않는다.
- 이전 버전(v0.2.3–v0.7.0)은 블록 하나를 `result.content[0].model_dump_json()`으로 넘겼다. 즉 `{"type":"text","text":"Error: ...","annotations":null,...}` 같은 JSON 문자열이고 isError 키는 없다(정확한 키 목록은 UNVERIFIED).
  - `https://github.com/openai/openai-agents-python/blob/v0.7.0/src/agents/mcp/util.py#L226`

**(2) 예외**

- `MCPError`(timeout, 연결 종료, JSON-RPC 오류)는 다시 raise한다. 그 밖의 예외는 `AgentsException("Error invoking MCP tool X on server 'S': <e>")`로 감싼다.
  - OAI `src/agents/mcp/util.py#L749-L783`
- HTTP 전송 오류는 `UserError("Failed to call tool 'X' on MCP server 'S': Connection timeout.")` 등으로 바꾼다.
  - OAI `src/agents/mcp/server.py#L1599-L1655`
- 이 예외들은 `_FailureHandlingFunctionToolInvoker.__call__`이 잡아 `failure_error_function`에 넘긴다.
  - OAI `src/agents/tool.py#L640`, `#L680-L697`, `#L2077-L2110`
- 기본 함수 `default_tool_error_function`은 v0.23.0부터 다음 고정 문구만 돌려준다.
  `"An error occurred while running the tool. Please try again."`
  - OAI `src/agents/tool.py#L1980-L1985`
  - docstring은 "Return a fixed error response without exposing the exception to the model."이다.
- v0.8.0–v0.22.0은 `f"An error occurred while running the tool. Please try again. Error: {str(error)}"`였다. v0.2.3–v0.6.0의 일반 FunctionTool도 같은 문구였다.
  - `https://github.com/openai/openai-agents-python/blob/v0.22.0/src/agents/tool.py#L1863-L1872`
- v0.7.0 이하에서는 MCP 도구에 failure 처리기가 붙지 않았다. 그래서 `AgentsException`이 run 전체를 중단시켰다.
  - `https://github.com/openai/openai-agents-python/blob/v0.7.0/src/agents/_run_impl.py#L1005-L1014`
- `failure_error_function=None`이면 예외를 그대로 raise한다. `RunConfig.tool_error_formatter`로 문구를 바꿀 수 있다.
  - OAI `docs/mcp.md` L72-L86, `src/agents/tool.py#L2092-L2110`

**(3) 재시도와 루프**

- `max_retry_attempts` 기본값은 0이다. 켜면 `list_tools`/`call_tool`의 **예외**만 지수 backoff로 재시도한다. isError는 재시도하지 않는다.
  - OAI `src/agents/mcp/server.py#L903`, `#L1292-L1301`
- 기본 `tool_use_behavior="run_llm_again"`이고 `DEFAULT_MAX_TURNS = 10`이다. 오류 결과 뒤에도 모델이 다시 호출할 수 있다.
  - OAI `src/agents/agent.py#L396-L401`, `src/agents/run_config.py#L45`

**(4) 도구 목록**

- 매 turn `get_all_tools` → `MCPUtil.get_all_function_tools` → `server.list_tools()`를 부른다. 그래서 `cache_tools_list=False`(기본)이면 도구 설명이 매 turn 새로 들어온다.
  - OAI `src/agents/run_internal/run_loop.py#L2712`, `src/agents/agent.py#L262-L284`, `src/agents/mcp/server.py#L916-L923`
- `list_changed` 구독 코드는 `src/agents/mcp/`에서 찾지 못했다(grep 결과 없음).
- 승인은 `require_approval` opt-in이다. 기본값 None은 False로 바뀐다.
  - OAI `src/agents/mcp/server.py#L749-L750`

**(5) 매핑**

| 경로 | 해당 조건 |
|---|---|
| isError (v0.8+) | E_unknown-like. 텍스트 원문만 가고 플래그는 없다 |
| 예외 (v0.23) | remedy-added. 원인은 빠지고 "Please try again."만 남는다. 본 연구의 `X_exception`과 달리 원인 문구가 없다 |
| 예외 (v0.8–v0.22) | remedy-added + X_exception-like(`... Please try again. Error: <msg>`) |

### 2.5 LangChain `langchain-mcp-adapters` (+ LangGraph ToolNode, `create_agent`)

**(1) isError 결과**

- 0.3.0 이상(main `52a4535`, 0.3.2)에서는 `_convert_call_tool_result`가 `if call_tool_result.isError: raise _MCPToolExecutionError(tool_content)`를 실행한다(LCA `langchain_mcp_adapters/tools.py#L226-L283`, L273-274).
- `handle_tool_errors=True`가 기본값이다(L366, L382-389, L547). 이때 `_handle_mcp_tool_error`가 변환된 content 블록을 **그대로** 돌려준다(L122-158).
- langchain_core `BaseTool`이 `ToolException`을 잡아 `status = "error"`를 붙인다.
  - LC `libs/core/langchain_core/tools/base.py#L1121-L1126`
- 결과는 `ToolMessage(content=[{"type":"text","text":"Error: tool execution failed"}], status="error")`다. 문구를 덧붙이지 않는다.
- content가 비어 있으면 `MCP tool returned an error with empty content.`로 대체한다(L70-95).
- 모델 쪽 인코딩:
  - ChatAnthropic: `"is_error": curr.status == "error"` (LC `libs/partners/anthropic/langchain_anthropic/chat_models.py#L361-L366`)
  - ChatOpenAI(vLLM 등 OpenAI 호환 포함): `content`, `role`, `tool_call_id`만 남기고 status는 버린다(LC `libs/partners/openai/langchain_openai/chat_models/base.py#L540-L547`)
- 0.2.2 이하에서는 텍스트를 이어 `raise ToolException(error_msg)`를 실행하고, `handle_tool_error`는 설정하지 않았다.
  - `https://github.com/langchain-ai/langchain-mcp-adapters/blob/langchain-mcp-adapters%3D%3D0.2.2/langchain_mcp_adapters/tools.py#L180-L189`, `#L426-L433`
  - 그래서 예외가 ToolNode까지 올라간다.

**(2) 예외와 ToolNode**

- adapter는 전송·세션 예외를 `ToolException`으로 바꾸지 않고 그대로 올린다(tools.py docstring L111-115, L470-487).
- LangGraph `ToolNode`:
  - `handle_tool_errors=True`이면 `TOOL_CALL_ERROR_TEMPLATE = "Error: {error}\n Please fix your mistakes."`이고 `error=repr(e)`다.
    - LG `libs/prebuilt/langgraph/prebuilt/tool_node.py#L115-L121`, `#L436-L438`
    - 예: adapter ≤0.2.2에서 isError면 `Error: ToolException('Error: tool execution failed')\n Please fix your mistakes.`가 되고, `status="error"` ToolMessage로 간다(L996-1030).
  - 기본값의 변화:
    - `prebuilt==1.0.1` 이하: `handle_tool_errors=True`.
      `https://github.com/langchain-ai/langgraph/blob/prebuilt%3D%3D1.0.0/libs/prebuilt/langgraph/prebuilt/tool_node.py#L299`
    - `prebuilt==1.0.2`부터: `_default_handle_tool_errors`가 기본값이다. `ToolInvocationError`(인자 검증 실패)만 메시지로 바꾸고 나머지는 다시 raise한다.
      LG `tool_node.py#L391-L399`, `#L751-L761`
- LangChain v1 `create_agent`는 `handle_tool_errors`를 지정하지 않고 ToolNode를 만든다. 그래서 위 기본값을 따른다.
  - LC `libs/langchain_v1/langchain/agents/factory.py#L1138-L1148`
- 결과:
  - adapter ≥0.3 + 최신 LangGraph: isError는 모델로 가고, 예외는 graph 실행을 중단시킨다.
  - adapter ≤0.2.2 + prebuilt ≥1.0.2: isError도 실행을 중단시킨다.

**(3) 재시도와 루프**

- adapter와 ToolNode는 재시도하지 않는다.
- opt-in `ToolRetryMiddleware`는 `max_retries=2`, `on_failure="continue"`이고, 소진되면 다음 문구를 쓴다.
  `f"Tool '{tool_name}' failed after {attempts_made} {attempt_word} with {exc_type}: {exc_msg}. Please try again."`
  - LC `libs/langchain_v1/langchain/agents/middleware/tool_retry.py#L136-L141`, `#L244-L261`
  - adapter ≥0.3의 isError는 예외로 올라오지 않으므로 이 middleware의 대상이 아니다(코드 경로상 추론, 실행 확인 안 함).
- ToolMessage를 받은 뒤 모델 노드로 돌아가므로 루프는 계속된다(recursion limit 기본값은 UNVERIFIED).

**(4) 도구 목록**

- `load_mcp_tools`/`convert_mcp_tool_to_langchain_tool`이 시작 시점의 `tool.description`으로 `StructuredTool`을 만든다(tools.py L519-536).
- adapter 소스에서 `list_changed` 처리를 찾지 못했다(grep 결과 없음).
- 승인은 기본으로 없다. LangChain v1의 HITL middleware는 opt-in이다(이번에 소스로 확인하지 않음, UNVERIFIED).

**(5) 매핑**

| 경로 | 해당 조건 |
|---|---|
| adapter ≥0.3 + OpenAI 호환 모델 | E_unknown-like(원문, 플래그 없음) |
| adapter ≥0.3 + Anthropic | native is_error |
| adapter ≤0.2.2 + ToolNode(handle_tool_errors=True) | remedy-added. 문구는 "Please fix your mistakes."이고 repr로 감싼다. 본 연구의 "Retry the same request."와 성격이 다르다. 이 문구는 행동을 바꾸라고 요구한다 |
| 예외 + ToolNode(True) | X_exception-like + remedy-added (`Error: McpError('...')\n Please fix your mistakes.`) |

### 2.6 LlamaIndex (`llama-index-tools-mcp`)

**(1) isError 결과**

- `McpToolSpec._create_tool_fn`이 `return await self.client.call_tool(tool_name, kwargs)`로 **`CallToolResult` 객체를 그대로** 돌려준다.
  - LI `llama-index-integrations/tools/llama-index-tools-mcp/llama_index/tools/mcp/base.py#L106-L114`
- `FunctionTool._parse_tool_output`은 알 수 없는 타입을 `TextBlock(text=str(raw_output))`로 바꾼다.
  - LI `llama-index-core/llama_index/core/tools/function_tool.py#L291-L329`, `#L374-L397`
- 그래서 모델은 isError든 성공이든 pydantic repr을 받는다. 패키지가 `mcp>=2.0.0,<3`에 고정돼 있으므로 v2 문자열이다(UNVERIFIED: 실제 설치 환경에서 실행하지 않음).
  `meta=None content=[TextContent(type='text', text='Error: tool execution failed', annotations=None, meta=None)] structured_content=None is_error=True result_type='complete'`
- `ToolOutput.is_error`는 False로 남는다(isError를 읽지 않음).
- FunctionAgent는 `ChatMessage(role="tool", blocks=...)`(LI `llama-index-core/llama_index/core/agent/workflow/function_agent.py#L148-L163`)로, ReActAgent는 `observation=str(tool_output.content)`(LI `.../agent/workflow/react_agent.py#L272-L275`)로 넘긴다.
- Anthropic LLM 통합 소스에서 `is_error` 매핑을 찾지 못했다(`llama-index-llms-anthropic/.../utils.py` grep 결과 없음).

**(2) 예외**

- `BaseWorkflowAgent._call_tool`이 예외를 잡는다. 결과는 `ToolOutput(content=str(e), ..., is_error=True)`다.
  - LI `llama-index-core/llama_index/core/agent/workflow/base_agent.py#L357-L392`
- `BasicMCPClient`는 `timeout=30`을 `read_timeout_seconds`로 쓴다(client.py L118-123, L226-276). 그래서 timeout이면 모델은 `Request 'tools/call' timed out`(v2 `MCPError` message)를 아무것도 덧붙이지 않은 채 받는다.
- 이름이 없는 도구에는 `Tool {name} not found. Please select a tool that is available.`를 준다(L636-660). 이 문구에는 remedy가 있지만, 실행 실패가 아니라 도구 이름 오류에만 쓰인다.

**(3) 재시도와 루프**

- 재시도는 없다.
- `DEFAULT_MAX_ITERATIONS = 20`이다(base_agent.py L67). 오류 뒤에도 루프가 계속된다.
- `BasicMCPClient.call_tool`은 호출마다 새 세션을 열고 initialize한다(client.py L300-327).

**(4) 도구 목록**

- `to_tool_list_async()`를 한 번 부를 때 설명을 고정한다(base.py L126-189).
- `list_changed` 처리는 찾지 못했다.
- 승인은 없다(UNVERIFIED: workflow HITL 기능 일반은 확인하지 않음).

**(5) 매핑**

| 경로 | 해당 조건 |
|---|---|
| isError | simple-chatbot과 같은 repr 계열이다. role은 tool이고 접두어는 없다. E_unknown 텍스트와 repr 안의 `is_error=True`가 함께 들어간다. JSON이 아니므로 E_json_flag와 정확히 같지는 않다 |
| 예외 | 문구가 덧붙지 않은 bare 예외 문자열. X_exception에서 `Error executing tool:` 접두어를 뺀 형태다 |

### 2.7 Pydantic AI (`MCPToolset`, fastmcp 기반)

**(1) isError 결과**

- 기본값은 `tool_error_behavior='retry'`다(PAI `pydantic_ai_slim/pydantic_ai/mcp.py#L777-L783`, L888).
- `direct_call_tool`은 `raise_on_error=False`로 호출한다(L1434). 그다음 다음 코드를 실행한다.

  ```python
  if result.is_error:
      ... message = ToolReturnPart(...).model_response_str(wrap_if_error=False)
      _raise_mcp_tool_error(message, self.tool_error_behavior)
  ```

  - L1478-1488. `'retry'`이면 `ModelRetry(message)`다(L1803-1817).
  - content가 비어 있으면 `Tool 'x' returned an error`를 쓴다.
- `RetryPromptPart.model_response()`는 `f'{description}\n\nFix the errors and try again.'`를 돌려준다.
  - PAI `pydantic_ai_slim/pydantic_ai/messages.py#L1852-L1874`
  - 그래서 모델은 `Error: tool execution failed\n\nFix the errors and try again.`를 받는다.
  - **isError 경로에 기본으로 remedy가 붙는다.** 조사한 클라이언트 중 유일하다.
- provider 인코딩:
  - OpenAI chat: `role='tool'`, `content=part.model_response()` (PAI `pydantic_ai_slim/pydantic_ai/models/openai.py#L2099-L2107`)
  - Anthropic: `tool_result(..., content=request_part.model_response(), is_error=True)` (`models/anthropic.py#L2425-L2435`)
  - Google: `functionResponse.response={'error': ...}` (`models/google.py#L1251-L1260`)
- `tool_error_behavior='failed'`이면 `ToolFailed`가 되고, `ToolReturnPart(outcome='failed')`로 바뀐다.
  - OpenAI chat에서는 `{"error":"<원문>"}` JSON으로 감싼다(messages.py L1600-1619).
  - Anthropic에서는 `is_error`가 붙는다(anthropic.py L2419).
  - remedy 문구는 없다. 문서 설명: "does not prepend retry/correction instructions" (`exceptions.py#L95-L107`)
- 이전 버전:
  - v0.2.10–v1.0.2: `'\n'.join(str(part) for part in content)`이고, 여기서 content는 텍스트로 바꾼 값이다.
  - v1.50–v1.107: TextContent의 `.text`를 모은다. content가 없으면 `'MCP tool call failed'`.
  - 두 경우 모두 `ModelRetry`이며 같은 retry 접미어가 붙는다.
  - `https://github.com/pydantic/pydantic-ai/blob/v1.0.2/pydantic_ai_slim/pydantic_ai/mcp.py#L223-L230`, `.../v1.107.1/...mcp.py#L1065-L1071`

**(2) 예외**

- `ToolError`는 behavior에 따라 처리한다. 프로토콜 수준 `McpError`는 `'failed'`여도 항상 `ModelRetry(str(e))`로 바꾼다(L1428-1448).
  - 따라서 v2 timeout이면 `Request 'tools/call' timed out\n\nFix the errors and try again.`로 추정한다. fastmcp가 timeout을 다른 타입으로 바꾸는지는 UNVERIFIED다.
  - 그 밖의 예외(예: HTTP 연결 오류)는 잡지 않으므로 run이 중단될 것으로 본다(UNVERIFIED).
- v1.0.2: `except McpError as e: raise exceptions.ModelRetry(e.error.message)`.

**(3) 재시도와 루프**

- 서버 호출을 자동으로 다시 실행하지는 않는다. `ModelRetry`는 모델에게 다시 시도하라고 요청할 뿐이다.
- agent의 tool retry 기본값은 1이다(`agent/__init__.py#L430-L437`, `tool_manager.py#L171`).
- 같은 도구에서 retry 예산을 넘기면 run이 중단된다. 메시지: `UnexpectedModelBehavior("Tool 'x' exceeded max retries count of 1. Consider raising the retry limit ...")` (`tool_manager.py#L301-L310`)
  - 즉 같은 도구에서 isError가 두 번 나면 중단이다.
  - 성공하면 카운터가 초기화되는지는 UNVERIFIED다.
- `'failed'` 모드는 retry 예산을 쓰지 않는다.

**(4) 도구 목록**

- `cache_tools=True`가 기본이다. `notifications/tools/list_changed`를 받거나 마지막 `__aexit__`에서 캐시를 비운다(mcp.py L799-810, L1297-1310).
- 승인은 opt-in이다(`ApprovalRequiredToolset`, `toolsets/approval_required.py`).

**(5) 매핑**

| 경로 | 해당 조건 |
|---|---|
| isError (기본) | remedy-added. 문구는 "Fix the errors and try again."이다. 본 연구의 "Retry the same request."와 달리 행동을 바꾸라고 요구한다 |
| isError + Anthropic | native is_error + remedy |
| `'failed'` 모드 + OpenAI | `{"error": "..."}` JSON 감싸기. E_json_flag와 같은 "JSON 안의 오류 표지"지만 키 이름과 내용 구성이 다르다 |
| McpError 예외 | X_exception-like + remedy |

## 3. 조건별 실재 사례

| 본 연구 조건 | 실제 클라이언트에서 같은 형태 | 비슷하지만 다른 형태 |
|---|---|---|
| E_unknown-like (원인 없는 평문, 플래그 없음) | OpenAI Agents SDK isError(v0.8+). adapter ≥0.3 + ChatOpenAI. MCP 튜토리얼 2025-06-18. 서버 측 Python SDK v2의 `Error executing tool <name>` | cli-client OpenAI의 `[tool error] ` 접두어 |
| E_json_flag-like (`{"content": [], "isError": true}` 원문 JSON) | **정확히 같은 출력은 찾지 못함** | simple-chatbot·LlamaIndex의 Python repr(`... is_error=True ...`, content 있음). cli-client Gemini의 `{content, isError:true}` 필드. Pydantic AI `'failed'` + OpenAI의 `{"error": ...}`. OpenAI Agents v0.2.3–v0.7.0의 TextContent JSON(플래그 없음) |
| native is_error flag | MCP 튜토리얼 2026-07-28, TS client-quickstart, cli-client Anthropic, LangChain+ChatAnthropic, Pydantic AI+Anthropic(remedy 포함) | Chat Completions(OpenAI·vLLM)에는 이런 필드가 없다. 본 연구 native 조건(Chat Completions `role:tool` 평문)에서는 원리상 재현할 수 없다 |
| X_exception-like (`Error executing tool: <msg>`) | simple-chatbot 예외 경로(정확히 같은 틀) | cli-client `Tool call failed: <msg>`. LlamaIndex bare `str(e)`. OpenAI Agents v0.8–v0.22 `... Please try again. Error: <msg>`. LangGraph `Error: <repr(e)>\n Please fix your mistakes.` |
| remedy-added | Pydantic AI(isError 기본). OpenAI Agents(예외 기본). LangGraph ToolNode(True). LangChain ToolRetryMiddleware(opt-in) | 문구 종류가 갈린다. 같은 행동을 반복하라는 문구("Please try again.")와 행동을 고치라는 문구("Please fix your mistakes.", "Fix the errors and try again.")다. 본 연구의 "Retry the same request."는 앞쪽에 가깝다 |
| reference-chatbot-like (1 round + 요약 강제) | MCP python-sdk `simple-chatbot`(system role 결과, 요약 지시, 두 번째 응답 미파싱) | MCP 튜토리얼(1 round + 한 번 더 호출, 요약 지시 없음) |

## 4. 논문에 쓸 수 있는 관찰과 주의점

1. **isError 텍스트는 거의 모든 클라이언트가 원문 그대로 넘긴다.** 원인을 덧붙이는 클라이언트는 없다. 그래서 서버가 원인 없는 문구를 주면 모델도 원인 없는 문구를 받는다. 공식 Python 서버 SDK v2는 예상하지 못한 예외에 `Error executing tool <name>`만 준다.
2. **플래그 전달은 provider가 결정한다.** Anthropic 계열만 네이티브 `is_error`가 있다. OpenAI Chat Completions 경로(vLLM 포함)에서는 OpenAI Agents SDK와 LangChain 모두 플래그를 버린다. 따라서 본 연구 native(Chat Completions) 결과는 "플래그 없는 원문" 클라이언트를 대표한다.
3. **remedy는 클라이언트가 실제로 덧붙인다.** Pydantic AI는 isError에, OpenAI Agents SDK는 예외에, LangGraph(True)는 둘 다에 붙인다. 다만 실제 문구는 "Please try again." 또는 "Fix the errors and try again." / "Please fix your mistakes."다. 행동을 고치라는 문구는 poisoned rule을 "고칠 방법"으로 읽게 할 수 있다. 그렇다면 억제가 아니라 촉진할 가능성도 있다. **가설일 뿐이며 시험하지 않았다.** 새 조건 후보로 둔다.
4. **버전에 따라 형식이 달라진다.**
   - 본 연구 text 조건은 python-sdk v1.x simple-chatbot 형식(`structuredContent=None isError=True`)이다. 현재 v2.3.0 형식은 `structured_content=None is_error=True result_type='complete'`이다. 논문에는 어느 버전을 기준으로 했는지 적어야 한다.
   - OpenAI Agents SDK의 예외 문구는 v0.23.0에서 원인 텍스트를 뺐다.
   - langchain-mcp-adapters는 0.3.0에서 isError를 실행 중단에서 모델 전달로 바꿨다.
   - LangGraph ToolNode 기본값은 prebuilt 1.0.2에서 True(remedy)에서 다시 raise로 바뀌었다.
5. **루프 중단 조건이 클라이언트마다 다르다.** Pydantic AI는 같은 도구에서 오류가 두 번 나면 run을 끝낸다. adapter ≤0.2.2 + 최신 ToolNode는 첫 isError에서 끝낸다. OpenAI Agents v0.7.0 이하는 예외에서 끝낸다. 이런 클라이언트에서는 "오류 뒤 다음 행동"이 아예 일어나지 않을 수 있다. 실재 노출 범위를 말할 때 함께 적어야 한다.
6. **도구 설명은 대부분 자동으로 노출되고, 승인은 기본으로 없다.** OpenAI Agents SDK는 기본 설정에서 매 turn `list_tools`를 다시 부른다. 그래서 서버가 설명을 바꾸면 다음 turn에 바로 반영된다. TS SDK와 Pydantic AI는 `list_changed`로 갱신한다. 조사한 7개 모두 승인 게이트는 opt-in이거나 없다.

## 5. UNVERIFIED 목록

- simple-chatbot v2에서 read timeout을 주지 않았을 때 timeout 예외가 생기는지(dispatcher 기본 timeout 값).
- v1 McpError timeout 문자열의 클래스 이름(`ClientRequest`).
- OpenAI Agents v0.2.3–v0.7.0의 `TextContent.model_dump_json()` 정확한 키 목록.
- LlamaIndex·Pydantic AI 출력 문자열을 실제 설치본으로 실행해 확인하지 않음(소스 경로로만 추론).
- Pydantic AI가 fastmcp를 거칠 때 timeout 예외의 타입과 문구, 그리고 McpError가 아닌 예외에서 run이 중단되는지.
- Pydantic AI retry 카운터가 성공하면 초기화되는지.
- LangChain v1 HITL middleware의 기본값, LangGraph recursion limit 기본값.
- LlamaIndex workflow에 일반 HITL 승인 기능이 있는지.
- 한 commit 범위 밖의 중간 버전 경계. 예를 들어 OpenAI Agents의 예외 문구가 v0.22.x와 v0.23.0 사이에서 정확히 언제 바뀌었는지는 태그 두 개로만 확인했다.
