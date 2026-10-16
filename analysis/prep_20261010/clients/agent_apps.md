# IDE·데스크톱 agent 앱이 실패한 MCP tool call을 모델에 넘기는 방식 (2026-10-10 조사)

대상: Cline, Roo Code, Continue, Goose, Zed, VS Code GitHub Copilot Chat

## 0. 조사 방법과 범위

- 모델 호출, MCP 서버 실행, Docker 실행은 하지 않았다.
  - 공개 저장소를 shallow·partial clone해 세션 scratchpad에 두고 소스를 직접 읽었다. 연구 폴더 밖이다.
  - 아래 "모델이 보는 텍스트"는 실행해서 관찰한 값이 아니라 코드에서 조립한 값이다.
  - 예시 입력은 두 가지다.
    - (A) 서버가 정상 응답으로 `CallToolResult{content:[{type:"text",text:"Error: tool execution failed"}], isError:true}`를 돌려준다.
    - (B) JSON-RPC 오류 응답, transport 끊김, timeout이 난다.
- 인용 URL은 모두 아래 commit에 고정했고, 줄 번호도 그 commit 기준이다.

| 클라이언트 | 기준 | commit | 커밋 시각 |
|---|---|---|---|
| Cline (현행, SDK 기반) | tag `v4.1.23` | `afaf4f2457ae467f2e0c8f4c9407967373e34569` | 2026-10-07 |
| Cline (구형 `use_mcp_tool` 경로, 마지막 v3) | tag `v3.89.2` | `e1bdeeff68e95734901c7a4b3a31753bae54a634` | 2026-06-11 |
| Cline (구형, 2025년 말 참고) | tag `v3.40.0` | `c22ea39dc17e5363f7ccd4189af538e64ce44950` | 2025-12-03 |
| Roo Code | tag `v3.54.0` | `27001b2b5aa47b65e8a6ba1914e0f4216be0ebb0` | 2026-05-15 |
| Continue (VS Code 확장 + `cn` CLI) | tag `v2.1.0-vscode` | `b238c1f11f26805f4387e10bab878b009f98e7a4` | 2026-06-18 |
| Goose (`block/goose`) | tag `v1.54.0` | `cd643d2126fffab4c6a6186905211ba868d6a657` | 2026-10-08 |
| Zed (native agent + context server) | tag `v1.23.2` | `c0199504b9cce79bc27524950022ed701bc3ebd5` | 2026-10-07 |
| VS Code core + Copilot Chat (`extensions/copilot`) | tag `1.141.0` | `2a59476c9bfcb90b3ddc372c36762471b7dfad1c` | 2026-10-06 |
| (보조) Vercel AI SDK, Cline v4가 씀 | `main` | `5a3c13cbb00de3b641af7b34bded5cfeaef286d5` | 2026-10-09 |
| (보조) rmcp, Goose가 씀 | `main` | `4048ac40e958fb1a7d614617a2ae8d26666ee2fa` | 2026-10-10 조회 |

- 버전을 고른 근거:
  - 각 기준 tag와 2026-10-09~10 시점 `main` HEAD에서 인용 파일을 `git diff`로 비교했고, 아래 인용 내용은 같았다.
  - Cline `McpHub.ts`만 3줄 달랐는데, 인용한 `callTool` 구간 줄 번호는 같았다.
- 저장소 상태:
  - Continue는 README에 "The `continuedev/continue` repository is no longer actively maintained and is read-only for all users."라고 적혀 있고, 마지막 릴리스는 "Final 2.0.0 Release" 계열이다.
  - Roo Code `main`의 마지막 커밋은 2026-05-15(`b867ec9`)다.
  - Copilot Chat 소스는 이제 `microsoft/vscode`의 `extensions/copilot/`에 들어 있다. 예전 단독 저장소 `microsoft/vscode-copilot-chat`의 현재 상태는 확인하지 않았다(UNVERIFIED).
- URL 접두어:
  - CLN4 = `https://github.com/cline/cline/blob/afaf4f2457ae467f2e0c8f4c9407967373e34569/`
  - CLN3 = `https://github.com/cline/cline/blob/e1bdeeff68e95734901c7a4b3a31753bae54a634/`
  - CLN340 = `https://github.com/cline/cline/blob/c22ea39dc17e5363f7ccd4189af538e64ce44950/`
  - ROO = `https://github.com/RooCodeInc/Roo-Code/blob/27001b2b5aa47b65e8a6ba1914e0f4216be0ebb0/`
  - CON = `https://github.com/continuedev/continue/blob/b238c1f11f26805f4387e10bab878b009f98e7a4/`
  - GSE = `https://github.com/block/goose/blob/cd643d2126fffab4c6a6186905211ba868d6a657/`
  - ZED = `https://github.com/zed-industries/zed/blob/c0199504b9cce79bc27524950022ed701bc3ebd5/`
  - VSC = `https://github.com/microsoft/vscode/blob/2a59476c9bfcb90b3ddc372c36762471b7dfad1c/`
  - AISDK = `https://github.com/vercel/ai/blob/5a3c13cbb00de3b641af7b34bded5cfeaef286d5/`
  - RMCP = `https://github.com/modelcontextprotocol/rust-sdk/blob/4048ac40e958fb1a7d614617a2ae8d26666ee2fa/`
  - 예: `CLN4 sdk/packages/agents/src/agent-runtime.ts#L2557-L2585` → `https://github.com/cline/cline/blob/afaf4f2…/sdk/packages/agents/src/agent-runtime.ts#L2557-L2585`
- 표기:
  - **[CODE]**: 소스에서 직접 확인.
  - **[DOCS]**: 공식 문서.
  - **[DERIVED]**: 코드를 조합해 추론했고 실행하지 않음.
  - **UNVERIFIED**: 확인하지 못함.
- 공통 전제: MCP TypeScript SDK의 `McpError` 메시지 형식 [CODE]
  - 형식은 `MCP error ${code}: ${message}`다. 1.12.0 `src/types.ts` L1269와 1.25.1 L2299에서 확인했다.
  - timeout은 `ErrorCode.RequestTimeout`(-32001)과 `'Request timed out'`이다(1.25.1 `src/shared/protocol.ts` L1191).
  - 각 클라이언트가 고정한 버전:
    - Cline `apps/vscode`: `^1.25.1`, `sdk/packages/core`: `^1.29.0`
    - Roo: `1.12.0`
    - Continue core: `^1.25.2`, CLI: `^1.24.0`
  - 1.29.0의 같은 줄은 경로가 달라 확인하지 못했다(UNVERIFIED).
  - 따라서 TS 기반 클라이언트에서 (B)의 예외 메시지는 보통 `MCP error -32603: <server message>` 또는 `MCP error -32001: Request timed out`이다. Cline은 timeout 문구를 바꾼다. 아래 Cline 절을 본다.

## 1. 핵심 결론

1. **조사한 6개 앱은 isError 결과를 모두 다르게 포맷한다. 우리 실험 조건 대부분에 실제 대응 사례가 있다.** [CODE]
   - E_json_flag 유사: **Cline v4**. MCP 결과 객체 전체를 JSON 문자열로 넣는다. 예: `{"content":[…],"isError":true}`. provider-native 플래그는 붙이지 않는다.
   - E_unknown 유사(평문 그대로):
     - Goose: 접두어 없음, 플래그 없음.
     - VS Code Copilot: 접두어 없음, 플래그 없음.
     - Roo Code와 Cline v3: `Error:\n` 접두어만 붙인다.
   - native is_error:
     - **Zed**: isError 결과에 Anthropic·Bedrock `tool_result.is_error=true`를 붙인다.
     - Goose, Cline v4: 예외 경로에서만 붙인다(Anthropic 계열).
   - remedy 추가:
     - **Continue IDE**: isError와 예외 모두에 "Please try something else or request further instructions."를 붙인다.
     - **Copilot**: 예외 경로에만 "Please check your input and try again."을 붙인다.
     - Cline v4: timeout 예외에만 사용자 대상 설정 안내 "Increase the "timeout" field …"를 붙인다.
   - isError가 아예 사라지는 경우: **Continue CLI(`cn`)**. `JSON.stringify(result.content)`만 성공 결과처럼 넘기므로 isError 정보가 없어진다.
2. **"Retry the same request"처럼 같은 호출을 다시 하라는 remedy는 어느 앱도 isError 결과에 붙이지 않는다.** [CODE]
   - Continue의 문구는 오히려 다른 방법을 찾으라는 쪽이다("try something else").
   - Copilot의 "check your input and try again"은 예외 경로에만 붙는다. MCP 서버가 isError로 응답하면 붙지 않는다.
3. **provider wire format 때문에 플래그가 사라진다.** [CODE]
   - native 플래그(Anthropic `is_error`)를 붙이는 경로도 OpenAI 호환 `role:"tool"` 메시지에는 오류 필드가 없어 텍스트만 남는다. Zed `open_ai`, Goose `openai`, AI SDK `openai-compatible`이 그렇다.
   - **Qwen3-14B와 gpt-oss-20b를 vLLM OpenAI 호환 endpoint로 붙이면 아래가 모델에게 보이는 전부다.**
     - Zed와 Goose(isError 경로): 평문.
     - Cline v4(isError 경로): `"isError":true`가 든 raw JSON 문자열.
     - Continue IDE: 래핑 문장 + remedy.
     - Copilot(예외 경로): 래핑 문장 + remedy.
4. **모든 앱이 오류 뒤에도 agent loop를 계속 돌리고, 다시 호출할지는 모델이 정한다.** [CODE]
   - isError 결과를 클라이언트가 자동으로 다시 실행하는 경우는 없다.
   - 자동 재시도는 VS Code core 하나다. 연결이 오류 상태이고 `shouldRetry`이면 예외 경로에서 1회 재시도한다(URL elicitation 오류도 1회).
5. **`reference-chatbot-like`(1라운드 후 강제 요약)에 해당하는 앱은 없다.** [CODE]
   - 가장 가까운 장치는 다음과 같다.
     - Cline SDK의 `reminderAfterIterations`: 기본 0, 즉 꺼져 있다.
     - Copilot의 `chat.agent.maxRequests` 도달 시 정지.
     - Goose의 max turns(기본 1000).
6. **tool description 변경 대응** [CODE]
   - `tools/list_changed`를 받아 목록을 다시 가져오는 앱: Cline v4, Goose, Zed, VS Code. 받지 않는 앱: Cline v3, Roo, Continue.
   - **description을 고정하거나 바뀌었을 때 다시 승인받는 장치는 어느 앱에서도 찾지 못했다.**
   - 승인 대화상자에 description 원문을 보여주는 앱은 VS Code뿐이다(readOnlyHint가 없는 도구).

## 2. 클라이언트별 상세

### 2.1 Cline 현행 (v4.x, `apps/vscode` + `sdk/packages`)

v4.0.0(2026-06-26)부터 VS Code 확장은 Cline SDK runtime을 쓰고, MCP 도구를 `server__tool` 이름의 native tool로 노출한다. 구형 `use_mcp_tool` 경로는 2.2절에 있다.

**(1) isError=true** [CODE]

- `McpHub.callTool`은 서버 결과를 손대지 않고 반환한다. `isError`도 객체 안에 남는다.
  - 근거: `return { ...result, content: result.content ?? [] }` — `CLN4 apps/vscode/src/services/mcp/McpHub.ts#L1673-L1752`, 반환은 L1737-L1740.
- SDK 도구 래퍼는 이 객체를 그대로 tool output으로 쓴다.
  - `CLN4 apps/vscode/src/sdk/vscode-runtime-builder.ts#L37-L45`
  - `CLN4 sdk/packages/core/src/extensions/mcp/tools.ts#L16-L48`
- runtime은 정상 반환을 `result = { output }`로 기록한다. runtime 차원의 `isError`는 **설정하지 않는다**. MCP의 `isError`를 끌어올리는 코드가 없다.
  - `CLN4 sdk/packages/agents/src/agent-runtime.ts#L2557-L2577`
  - tool-result part 생성: L2618-L2626
- 모델 요청 직전 `beforeModel` hook이 메시지를 provider 형식으로 왕복 변환한다.
  - `CLN4 sdk/packages/core/src/runtime/orchestration/session-runtime-orchestrator.ts#L1249-L1268`
  - 이때 객체 output은 `JSON.stringify(output)` 문자열이 되고, `is_error`는 `undefined`로 남는다.
    - `CLN4 sdk/packages/core/src/session/persisted-tool-result-content.ts#L9-L24`
    - `CLN4 sdk/packages/core/src/runtime/config/agent-message-codec.ts#L225-L235`, `#L296-L303`
  - 문자열이므로 AI SDK에는 `{type:"text"}`로 들어간다. 문자열이 아닌 객체였더라도 `json` 타입이 되어 결국 JSON 문자열로 직렬화된다.
    - `CLN4 sdk/packages/shared/src/llms/ai-sdk-format.ts#L544-L637`
    - `AISDK packages/openai-compatible/src/chat/convert-to-openai-compatible-chat-messages.ts`의 `case 'json'` → `JSON.stringify(output.value)`
- **모델이 보는 텍스트** [DERIVED]: `{"content":[{"type":"text","text":"Error: tool execution failed"}],"isError":true}`
  - 키 순서는 MCP SDK zod 스키마 순서를 따를 것으로 보지만 실행 확인은 하지 않았다(UNVERIFIED). 서버가 `structuredContent`나 `_meta`를 보내면 그 키도 같이 들어간다.
  - Anthropic이든 OpenAI 호환이든 native error 플래그는 붙지 않는다.
  - 클라이언트가 덧붙이는 지시문이나 remedy는 없다.

**(2) 예외** [CODE]

- runtime이 예외를 잡아 `output: { error: <message> }, isError: true`로 만든다.
  - `CLN4 sdk/packages/agents/src/agent-runtime.ts#L2578-L2585`
- 왕복 변환 뒤에는 `content = '{"error":"…"}'`, `is_error = true`가 되고, AI SDK에는 `error-text`로 간다.
  - Anthropic provider는 `is_error: true`를 붙인다. `AISDK packages/anthropic/src/convert-to-anthropic-prompt.ts#L668-L678`
  - OpenAI 호환은 `case 'error-text'`에서 문자열만 넘긴다(위 파일).
  - Cline이 실제로 고정한 AI SDK 버전에서 같은 동작인지는 확인하지 않았다(UNVERIFIED).
- timeout은 메시지를 바꾼다. `MCP request to "<server>" timed out after <s>s. Increase the "timeout" field (in seconds) for this server in cline_mcp_settings.json.`
  - `CLN4 sdk/packages/shared/src/mcp.ts#L40-L51`
  - `CLN4 apps/vscode/src/services/mcp/McpHub.ts#L1750`, `augmentMcpTimeoutError`
- **모델이 보는 텍스트** [DERIVED]
  - JSON-RPC 오류: `{"error":"MCP error -32603: <message>"}`
  - timeout: `{"error":"MCP error -32001: MCP request to \"srv\" timed out after 60s. Increase the \"timeout\" field (in seconds) for this server in cline_mcp_settings.json."}`
  - 플래그: Anthropic이면 `is_error:true`, OpenAI 호환이면 없음.
  - 연결 없음이나 서버 비활성은 `No connection found for server: … Please make sure to use MCP servers available under 'Connected MCP Servers'.` 같은 문장이 된다(`McpHub.ts#L1680-L1697`).

**(3) 재시도와 loop** [CODE]

- 도구 정의에는 기본값 `retryable: true, maxRetries: 3`이 있다(`CLN4 sdk/packages/shared/src/tools/create.ts#L133-L135`). 그러나 agent runtime이나 core에서 이 값을 읽는 곳은 grep으로 찾지 못했다. **자동 재실행은 없는 것으로 판단한다.**
- loop는 tool result를 붙인 뒤 다음 모델 턴으로 넘어간다.
- 연속 실수 추적:
  - "모든 tool call이 실패한 턴"은 mistake로 센다. 기본 상한은 6이고, 도달하면 정지하거나 hook에 결정을 맡긴다.
    - `CLN4 sdk/packages/shared/src/agents/types.ts#L252-L258`
    - `CLN4 sdk/packages/core/src/runtime/orchestration/session-runtime-orchestrator.ts#L1321-L1322`, `#L1369-L1377`
  - 실패 판정은 runtime `isError === true`일 때만 한다. 그래서 **MCP isError 결과는 성공 턴으로 세지고 mistake 카운터를 0으로 되돌린다.** 예외만 mistake로 센다.
- `reminderAfterIterations`는 기본 0(꺼짐)이다. 켜면 "REMINDER: If you have gathered enough information … provide your final answer now without using any more tools."를 넣는다(`types.ts#L259-L270`).

**(4) list_changed와 승인** [CODE]

- `ToolListChangedNotificationSchema`를 받으면 debounce한 뒤 목록을 다시 가져온다. 이어서 active session을 조용히 재시작해 도구를 다시 만든다.
  - `CLN4 apps/vscode/src/services/mcp/McpHub.ts#L767-L768`
  - `CLN4 apps/vscode/src/sdk/sdk-mcp-coordinator.ts#L30-L41`
  - description 변경 여부를 사용자에게 묻지 않는다.
- 승인:
  - 모든 MCP 도구는 `autoApprove: false` 정책이다. 실제 승인 여부는 전역 토글 하나(`settings.actions.useMcp`)가 정하고, "there is no per-tool opt-in".
    - `CLN4 apps/vscode/src/sdk/sdk-tool-policies.ts#L30-L37`, `#L62-L65`
  - MCP 설정 화면은 tool description을 보여준다(`CLN4 apps/vscode/webview-ui/src/components/mcp/configuration/tabs/installed/server-row/McpToolRow.tsx#L69-L77`).
  - 승인 프롬프트에 description이 나오는지는 확인하지 않았다(UNVERIFIED).

### 2.2 Cline 구형 (v3.x, `use_mcp_tool` 경로, v3.89.2까지)

**(1) isError=true** [CODE]

- 결과 텍스트 앞에 `"Error:\n"`만 붙인다: `(toolResult?.isError ? "Error:\n" : "") + content…join("\n\n")`
  - `CLN3 apps/vscode/src/core/task/tools/handlers/UseMcpToolHandler.ts#L182-L196`
  - 2025-12 v3.40.0에서도 같다: `CLN340 src/core/task/tools/handlers/UseMcpToolHandler.ts#L182`
- 결과는 `"<description> Result:\n<text>"`로 감싼다(`CLN3 apps/vscode/src/core/task/tools/utils/ToolResultUtils.ts#L47-L50`).
  - native tool call이면 `tool_result`에 넣고 `is_error`는 붙이지 않는다(`#L79-L84`).
  - XML 모드면 일반 text block이 된다(`#L69-L73`).
- **모델이 보는 텍스트** [DERIVED]: `[use_mcp_tool for '<server>'] Result:\nError:\nError: tool execution failed`

**(2) 예외** [CODE]

- `return \`Error executing MCP tool: ${message}\`` — `UseMcpToolHandler.ts#L213-L215`(v3.40.0은 L210)
- **모델이 보는 텍스트** [DERIVED]: `[use_mcp_tool for '<server>'] Result:\nError executing MCP tool: MCP error -32001: Request timed out`

**(3)~(4)** [CODE]

- 오류 뒤에도 loop가 이어진다.
- mistake count는 인자 누락과 JSON 파싱 실패에만 늘어난다(`#L56-L77`).
  - 잘못된 JSON 인자에는 "Invalid JSON argument used with … Please retry with a properly formatted JSON argument."라는 remedy를 붙인다(`CLN3 apps/vscode/src/core/prompts/responses.ts#L126-L127`). MCP 오류에는 붙이지 않는다.
- 호출마다 승인을 받는다. 예외는 전역 auto-approve와 도구별 `autoApprove`다(`#L89-L143`). 승인 메시지에는 server, tool, arguments만 들어간다.
- v3.89.2 `McpHub.ts`와 v3.40.0 `McpHub.ts`에는 `ToolListChanged` 처리가 없다(grep 결과 없음).

### 2.3 Roo Code (v3.54.0)

native tool call(`mcp--server--tool`)은 `mcp_tool_use` 블록에서 `UseMcpToolTool`로 전달된다(`ROO src/core/assistant-message/presentAssistantMessage.ts#L103-L264`).

**(1) isError=true** [CODE]

- `(toolResult.isError ? "Error:\n" : "") + outputText` — `ROO src/core/tools/UseMcpToolTool.ts#L311-L349`, 접두어는 L327-L329.
- `pushToolResult`는 `tool_result`를 만들 때 `is_error`를 넣지 않는다(`presentAssistantMessage.ts#L134-L180`, 특히 L167-L172).
  - Roo가 `is_error: true`를 쓰는 곳은 거부되거나 중단된 tool call뿐이다(L116-L122, L395-L400 등).
- **모델이 보는 텍스트** [DERIVED]: `Error:\nError: tool execution failed`. 플래그와 remedy는 없다.

**(2) 예외** [CODE]

- `McpHub.callTool`은 예외를 그대로 던진다. 기본 timeout은 60s다(`ROO src/services/mcp/McpHub.ts#L1730-L1769`).
- `execute`의 catch가 `handleError("executing MCP tool", error)`를 호출한다(`UseMcpToolTool.ts#L78-L79`).
- `handleError`는 `Error ${action}: ${JSON.stringify(serializeError(error))}`를 만든다. `serializeError`는 `serialize-error` 패키지이고, 결과는 다시 `formatResponse.toolError`로 감싼다.
  - `presentAssistantMessage.ts#L220-L231`
  - `ROO src/core/prompts/responses.ts#L26-L31`
- **모델이 보는 텍스트** [DERIVED]: `{"status":"error","message":"The tool execution failed","error":"Error executing MCP tool: {\"name\":\"McpError\",\"message\":\"MCP error -32001: Request timed out\",\"stack\":\"…\",\"code\":-32001,…}"}`
  - 오류 객체 안 키 순서와 `stack` 포함 여부는 `serialize-error` 동작에 따른다(UNVERIFIED).
  - 플래그는 없다.
  - 클라이언트 고정 문구 `"The tool execution failed"`가 들어간다. 이는 우리 E_unknown 문구와 거의 같다.

**(3)~(4)** [CODE]

- 오류 뒤에도 loop가 이어진다. 자동 재시도는 없다.
- `consecutiveMistakeCount`는 서버·도구 이름 검증이나 인자 오류 때만 늘어난다(`UseMcpToolTool.ts#L101-L223`). 기본 상한은 3이다(`ROO packages/types/src/provider-settings.ts#L29`).
- 호출마다 승인을 받는다. 도구별 `alwaysAllow`가 있으면 생략한다(`ROO src/core/auto-approval/mcp.ts`). 승인 메시지는 `{type, serverName, toolName, arguments}`다(`UseMcpToolTool.ts#L55-L63`).
- `McpHub.ts`에는 `list_changed` 처리가 없다(grep 결과 없음). 설정 화면에서 description을 보여주는지는 UNVERIFIED다.

### 2.4 Continue (v2.1.0-vscode; IDE 확장과 `cn` CLI)

**(1) isError=true — IDE 확장** [CODE]

- core가 `if (response.isError === true) throw new Error(JSON.stringify(response.content));`로 예외를 만든다(`CON core/tools/callTool.ts#L102-L113`).
  - 바깥 catch는 이를 `errorMessage`로 돌려준다(`#L263-L278`).
- GUI는 이 문자열을 다음처럼 감싼 context item으로 바꾼다(`CON gui/src/redux/thunks/callToolById.ts#L97-L111`). 이어서 model에 다시 보낸다(L139-L146).
  - `` `${toolName} failed with the message: ${error.message}\n\nPlease try something else or request further instructions.` ``
- tool 메시지는 `role:"tool"`이고 content는 context item을 `"\n\n"`로 이은 문자열이다. 오류 필드는 없다.
  - `CON gui/src/redux/util/constructMessages.ts#L131-L158`
  - `CON core/util/messageContent.ts#L34-L36`
  - `core/llm` 안에 `is_error` 사용처가 없다(grep).
- **모델이 보는 텍스트** [DERIVED]: `<tool> failed with the message: [{"type":"text","text":"Error: tool execution failed"}]\n\nPlease try something else or request further instructions.`
  - isError 플래그는 사라지고 content 배열의 raw JSON만 남는다.
  - 클라이언트 remedy 문장이 붙는다.

**(1') isError=true — `cn` CLI** [CODE]

- MCP 도구의 `run`은 `return JSON.stringify(result?.content) ?? ""`다(`CON extensions/cli/src/tools/index.tsx#L192-L211`). isError를 보지 않으므로 **성공 결과로 처리된다**.
- **모델이 보는 텍스트** [DERIVED]: `[{"type":"text","text":"Error: tool execution failed"}]`. 상태는 `done`이다.

**(2) 예외** [CODE]

- IDE: 같은 래퍼를 쓴다. `<tool> failed with the message: MCP error -32001: Request timed out\n\nPlease try something else or request further instructions.`
  - MCP timeout은 `client.options.timeout`을 따른다(`callTool.ts#L102-L109`).
- CLI: `` `Error executing tool ${call.name}: ${message}` `` 이고 status는 `errored`다(`CON extensions/cli/src/stream/streamChatResponse.helpers.ts#L587-L600`).
- 출력도 결과도 없으면 `"There was an error calling the tool."`를 쓴다(`CON core/tools/constants.ts#L1-L4`).

**(3)~(4)** [CODE]

- 오류 뒤 `streamResponseAfterToolCall`로 바로 모델을 다시 부른다. 자동 재시도는 없다.
- 기본 tool policy는 `allowedWithPermission`이다(`CON gui/src/redux/slices/uiSlice.ts#L34`).
- `MCPConnection.ts`의 notification handler는 주석 처리돼 있다(L286). **list_changed를 처리하지 않는다.** description 표시 방식은 UNVERIFIED다.

### 2.5 Goose (v1.54.0)

**(1) isError=true** [CODE]

- MCP 결과는 `Ok(CallToolResult{is_error: Some(true), …})` 그대로 기록된다.
  - `GSE crates/goose/src/agents/extension_manager/lease.rs#L654-L720`
  - `GSE crates/goose/src/agents/state_machine/ops_toolcalling.rs#L240-L265`
  - `is_error`는 telemetry span 표시에만 쓰인다.
- provider formatter의 `Ok` 분기는 **`is_error`를 보지 않는다**.
  - Anthropic: text들을 `"\n"`로 이어 `tool_result.content`에 넣고 `is_error` 필드는 없다. `GSE crates/goose-provider-types/src/formats/anthropic.rs#L331-L423`
  - OpenAI: text들을 `" "`로 이어 `role:"tool"`에 넣는다. `GSE crates/goose-provider-types/src/formats/openai.rs#L359-L403`
- **모델이 보는 텍스트** [DERIVED]: `Error: tool execution failed`. 서버 텍스트 그대로이고 플래그와 remedy는 없다.

**(2) 예외** [CODE]

- `ServiceError`는 `ErrorData`로 바뀐다. JSON-RPC 오류는 원래 `ErrorData`를 쓰고, 나머지는 `ErrorData::new(INTERNAL_ERROR(-32603), e.to_string())`이 된다(`lease.rs#L699-L702`).
  - rmcp `Display`는 `"{code}: {message}"`(+`({data})`)다(`RMCP crates/rmcp/src/error.rs#L4-L12`).
  - timeout 문구는 `"request timeout after {chrono::Duration}"`이다(`RMCP crates/rmcp/src/service.rs#L92-L93`).
- Anthropic: `content: "Error: {e}"`, `is_error: true` — `anthropic.rs#L425-L432`
- OpenAI: `"The tool call returned the following error:\n{e}"` — `openai.rs#L404-L411`
  - Google `formats/google.rs`와 Databricks `formats/databricks.rs#L116`도 같은 계열이다.
- **모델이 보는 텍스트** [DERIVED]
  - Anthropic: `Error: -32603: <message>` + `is_error:true`
  - OpenAI 호환: `The tool call returned the following error:\n-32603: <message>`
  - timeout은 `-32603: request timeout after PT300S` 꼴이다. duration 표기는 UNVERIFIED다.

**(3)~(4)** [CODE]

- 오류 뒤에도 loop가 이어진다. 자동 재시도는 없다.
  - `ops_retry.rs`는 recipe 성공 검사용 재시도다.
  - `ops_exit_on_error.rs`는 provider 오류가 대화 끝에 남은 경우에만 동작한다.
- 기본 `DEFAULT_MAX_TURNS = 1000`이다(`GSE crates/goose/src/agents/agent.rs#L88`).
- `tools/list_changed`를 받으면 `tools_version`을 올려 캐시를 무효로 만든다. 다음 목록 조회 때 다시 가져온다.
  - `GSE crates/goose/src/agents/mcp_client.rs#L208-L210`, `#L358-L359`
  - `extension_manager/mod.rs#L141`
- 기본 모드 `GooseMode::Auto`는 "Automatically approve tool calls"다. **기본 설정에서는 승인이 없다**(`GSE crates/goose-provider-types/src/goose_mode.rs#L22-L33`).
- prompt injection 검사기 `SECURITY_PROMPT_ENABLED`는 기본 false다(`GSE crates/goose/src/security/mod.rs#L71-L72`).
- description을 사용자에게 보여주는지는 UNVERIFIED다.

### 2.6 Zed (v1.23.2, native agent의 context server 도구)

**(1) isError=true** [CODE]

- isError 결과를 오류로 바꾼다.
  - `if response.is_error == Some(true) { let error_message: String = response.content.iter().filter_map(|c| c.text()).collect(); return Err(anyhow!(error_message).into()); }`
  - `ZED crates/agent/src/tools/context_server_registry.rs#L393-L397`
  - text들은 구분자 없이 이어 붙인다.
- `Err(output) => (true, output)`로 `LanguageModelToolResult{is_error: true, content: [Text(error.to_string())]}`가 된다.
  - `ZED crates/agent/src/thread.rs#L3710-L3760`, 특히 L3750
  - `ZED crates/language_model_core/src/request.rs#L251-L255`
- provider별 처리:
  - Anthropic: `is_error: tool_result.is_error`를 전달한다(`ZED crates/anthropic/src/completion.rs#L257-L260`). Bedrock도 반영한다.
  - OpenAI 계열: `RequestMessage::Tool{content}`만 보낸다(`ZED crates/open_ai/src/completion.rs#L193`).
- **모델이 보는 텍스트** [DERIVED]
  - Anthropic: `Error: tool execution failed` + `is_error:true`
  - OpenAI 호환: `Error: tool execution failed`
  - 접두어와 remedy는 없다.

**(2) 예외** [CODE]

- JSON-RPC 오류는 `Err(anyhow!(error.message))`다. code를 버리고 message만 남긴다.
- timeout은 `"Context server request timeout"`이고 기본 60s다.
  - `ZED crates/context_server/src/client.rs#L454-L457`, `#L481-L484`, `#L30`
- 사용자 취소는 `"MCP tool cancelled by user"`다.
- (1)과 같은 `is_error:true` 경로를 탄다. **isError와 예외를 모델이 구분할 수 없다.**

**(3)~(4)** [CODE]

- 오류 뒤에도 loop가 이어진다.
- `MAX_RETRY_ATTEMPTS = 4`는 completion(provider) 오류용이다(`thread.rs`). tool 재시도나 연속 실패 상한은 찾지 못했다.
- `notifications/tools/list_changed`를 받으면 `reload_tools_for_server`를 호출한다(`context_server_registry.rs#L143-L156`, `#L170`).
- 호출마다 권한을 확인한다.
  - 기본값은 `"tool_permissions": {"default": "confirm"}`이고, 주석에 "The per-tool "default" also applies to MCP tools."라고 적혀 있다(`ZED assets/settings/default.json#L1234-L1239`).
  - 선택지는 "Always for <tool> MCP tool"과 "Only this time"이다(`thread.rs#L5810`~).
  - 확인 창 제목은 도구 이름과 입력으로 만든다(`format_mcp_initial_title`). description 표시 여부는 UNVERIFIED다.

### 2.7 VS Code + GitHub Copilot Chat (1.141.0)

**(1) isError=true** [CODE]

- VS Code core의 `McpToolImplementation.invoke`는 `isError`를 UI용 `toolResultDetails.isError`에만 넣는다(`VSC src/vs/workbench/contrib/mcp/common/mcpLanguageModelToolContribution.ts#L276-L281`).
  - 모델용 `result.content`에는 text를 그대로 넣는다(L333-L339). `toolResultError`는 설정하지 않는다.
  - `structuredContent`가 있으면 text 대신 `JSON.stringify(structuredContent)`를 넣는다(L389-L392).
- Copilot은 이 결과를 그대로 렌더링한다(`VSC extensions/copilot/src/extension/prompts/node/panel/toolCalling.tsx#L343`).
- Messages API(Anthropic) 경로의 `tool_result`에는 `is_error`가 없다(`VSC extensions/copilot/src/platform/endpoint/node/messagesApi.ts#L393-L397`). `extensions/copilot/src` 전체에서 tool_result용 `is_error`는 쓰이지 않는다(grep).
- **모델이 보는 텍스트** [DERIVED]: `Error: tool execution failed`. 플래그와 remedy는 없다.

**(2) 예외** [CODE]

- JSON-RPC 오류는 `MpcResponseError`가 된다. 메시지는 `` `MPC ${code}: ${message}` ``이고, "MPC"는 원문 철자 그대로다.
  - `VSC src/vs/workbench/contrib/mcp/common/mcpTypes.ts#L930-L934`
  - `mcpServerRequestHandler.ts#L243`
- tools service는 `toolResultError`를 기록한 뒤 예외를 다시 던진다(`VSC src/vs/workbench/contrib/chat/browser/tools/languageModelToolsService.ts#L785-L808`).
- Copilot은 이를 잡아 다음 문장으로 바꾼다.
  - `` `ERROR while calling tool: ${errorMessage}${toolErrorSuffix}` ``, 여기서 `toolErrorSuffix = '\nPlease check your input and try again.'`
  - `toolCalling.tsx#L236`, `#L355-L366`, `#L674-L681`
- **모델이 보는 텍스트** [DERIVED]: `ERROR while calling tool: MPC -32603: <message>\nPlease check your input and try again.` 플래그는 없다.
- 클라이언트 측 기본 request timeout이 있는지는 확인하지 못했다(UNVERIFIED).

**(3)~(4)** [CODE]

- 자동 재시도는 예외 경로에서 최대 1회다.
  - URL elicitation이 필요하다는 오류일 때.
  - 연결 상태가 `Error`이고 `shouldRetry`일 때.
  - `VSC src/vs/workbench/contrib/mcp/common/mcpServer.ts#L1356-L1421`, 특히 L1406-L1418
  - isError 결과는 다시 실행하지 않는다.
- loop는 계속되다가 `toolCallLimit`(`chat.agent.maxRequests`)에 닿으면 멈추고 사용자에게 계속할지 묻는다(`VSC extensions/copilot/src/extension/intents/node/toolCallingLoop.ts#L1449-L1458`).
- `notifications/tools/list_changed`를 받으면 `updateTools`로 다시 가져온다.
  - `mcpServerRequestHandler.ts#L374-L375`
  - `mcpServer.ts#L1224-L1227`
- 승인:
  - readOnlyHint가 없는 MCP 도구는 확인 창을 띄운다. `confirm.message = new MarkdownString(tool.definition.description)`이므로 **description 원문이 확인 창에 나온다.**
  - 함께 나오는 경고: "Note that MCP servers or malicious conversation content may attempt to misuse '{0}' through tools."
  - "Always allow"(`allowAutoConfirm = true`)를 고를 수 있다.
  - `mcpLanguageModelToolContribution.ts#L213-L261`
  - [DOCS] "The confirmation dialog will be shown for all tools that are not marked with the readOnlyHint annotation." (code.visualstudio.com, Use tools in chat — 검색 결과 요약으로 확인했다. 원문 페이지는 404였다.)

## 3. 실험 조건과의 대응

| 조건 | 해당 앱과 경로 | 실제 형식 (A: isError, B: 예외) |
|---|---|---|
| **E_unknown-like** (설명 없는 평문 오류) | Goose (A), VS Code Copilot (A), Zed + OpenAI 호환 (A·B) | 서버 텍스트 그대로. Roo와 Cline v3는 `Error:\n` 접두어만 붙는다 (A). |
| **E_json_flag-like** (raw JSON + isError) | **Cline v4 (A)** | `{"content":[…],"isError":true}` 문자열 그대로. Continue IDE·CLI는 isError 없이 `content` 배열 JSON만 넘긴다 (A). |
| **native is_error** | **Zed + Anthropic·Bedrock (A·B)**, Goose + Anthropic (B), Cline v4 + Anthropic (B) | `tool_result.is_error=true`. OpenAI 호환(vLLM)에서는 어느 앱이든 사라진다. |
| **X_exception-like** | 모든 앱의 (B) | Cline v4 `{"error":"MCP error …"}`, Cline v3 `Error executing MCP tool: …`, Roo `{"status":"error","message":"The tool execution failed","error":"Error executing MCP tool: {serialized McpError}"}`, Continue CLI `Error executing tool <name>: …`, Goose `Error: <code>: <msg>` / `The tool call returned the following error:\n…`, Zed `<msg>`, Copilot `ERROR while calling tool: MPC …` |
| **remedy-added** | **Continue IDE (A·B)**: "Please try something else or request further instructions." / **Copilot (B만)**: "Please check your input and try again." / Cline v4 timeout (B만): "Increase the "timeout" field …" | 같은 호출을 다시 하라는 "Retry the same request"류는 없다. Continue는 다른 방법을 권하고, Copilot은 입력 점검 후 재시도를 권한다. |
| **reference-chatbot-like** (1라운드 후 강제 요약) | 해당 없음 | 모든 앱이 multi-turn loop를 계속 돈다. 가까운 장치: Cline `reminderAfterIterations`(기본 꺼짐), Copilot `maxRequests` 정지, Goose max turns 1000. |

논문에 쓸 만한 관찰 [DERIVED]:

- 우리 E_unknown 문구 `Error: tool execution failed`와 실제 앱 문구가 거의 겹친다. Roo Code 예외 경로에는 클라이언트 고정 문구 `"message":"The tool execution failed"`가 있다. Continue에는 `ERRORED_TOOL_CALL_OUTPUT_MESSAGE = "There was an error calling the tool."`가 있다. 따라서 "지시 없는 오류" 조건은 인위적인 설정이 아니다.
- remedy 효과를 주장할 때 범위를 정확히 적어야 한다. 실제 앱의 remedy 문구는 "try something else"(Continue)나 "check your input and try again"(Copilot, 예외만)이다. 우리 remedy("Retry the same request")와 같은 문구는 없다.
- Cline v4와 Continue CLI는 isError를 성공 결과처럼 취급한다. Cline v4는 mistake 카운터를 0으로 되돌리고, Continue CLI는 status를 `done`으로 둔다. 따라서 "오류가 반복되면 loop가 멈추는" 안전장치가 isError 경로에서는 작동하지 않는다.
- description 변경(rug pull)에 대해서는 네 앱이 list_changed를 자동 반영한다. 다시 승인받는 앱은 없다. VS Code만 매 호출 확인 창에 현재 description을 보여준다. readOnlyHint가 있는 도구와 "Always allow"를 고른 경우는 예외다.

## 4. 확인하지 못한 것 (UNVERIFIED 모음)

- Cline v4 raw JSON의 키 순서. Cline이 실제로 번들한 AI SDK 버전에서도 `error-text`가 `is_error:true`로 가는지.
- Roo `serialize-error` 출력의 키 순서와 stack 포함 여부.
- Goose timeout duration 문자열(`PT300S` 꼴인지). Goose, Zed, Roo, Continue에서 tool description을 UI에 보여주는지.
- VS Code MCP 클라이언트의 기본 request timeout. `chat.agent.maxRequests` 기본값. auto-approve 관련 설정 이름과 기본값(소스 stub만 확인).
- `microsoft/vscode-copilot-chat` 단독 저장소의 현재 상태. MCP TS SDK 1.29.0의 `McpError` 메시지 형식. 1.12.0과 1.25.1은 확인했다.
- 실제 실행으로 확인한 출력은 없다. "모델이 보는 텍스트"는 모두 [DERIVED]다.
