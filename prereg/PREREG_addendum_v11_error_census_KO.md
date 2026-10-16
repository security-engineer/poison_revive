# 사전 등록 부록 v11: 실제 MCP 서버 코드가 모델에게 돌려주는 오류 문구 조사

- 작성: 2026-10-13. 원고의 단계 이름은 S12다. 모델 호출이 없는 코드 조사다.
- 분류 규칙과 코드는 결과를 세기 전에 이 문서와 `analysis/prep_20261010/v11/error_census.py`로 고정하고 commit한다. 오류 문구를 모으거나 센 결과는 아직 없다.

## 왜 하는가

이 연구의 오류는 모두 주입한 것이다. 심사에서 가장 먼저 나올 질문은 "실제 서버가 이런 오류를 내느냐"다. 앞선 결과에서 재활성화를 가장 많이 일으킨 것은 원인을 말하지 않거나 호출을 탓하는 오류였고, 원인을 밝힌 오류(권한 없음, 시간 초과)는 가장 적게 일으켰다. 실제 서버 코드의 오류 문구가 어느 쪽에 많은지 센다.

## 대상(고정 버전의 원본 코드)

MCPTox 서버 45개 가운데 원본 코드가 이 장비에 고정 버전으로 있는 22개(사례 756/1,348개)다. 출처는 `/workspace/TAEYUN/tp-redteam/local/vendor/`이고, 버전은 그 저장소의 `images/README.md`에 적힌 것과 같다.

| 묶음 | 서버 |
|---|---|
| modelcontextprotocol/servers `6f7c7f0` | FileSystem, Memory, Fetch, Sequential Thinking, Everything(같은 저장소의 이 commit 판) |
| servers-archived `9be4674` | AWSKnowledgeBase, BraveSearch, EverArt, GoogleDrive, Github, Gitlab, Google Maps, Puppeteer, Redis, Sentry, Slack, SQLite |
| PyPI sdist | Git(`mcp-server-git` 2025.1.14) |
| 개별 저장소 | Commander(DesktopCommanderMCP v0.1.39), Email(mcp-mail `ed683c9`), ClickHouse(`4cea684`), QuickChart(v1.0.6) |

빠진 서버 23개는 SaaS 전용이거나 코드가 이 장비에 없다. 결과는 이 22개에 한정한다.

## 무엇을 모으나

- 서버 코드(테스트 제외)에서 도구 호출이 실패할 때 모델에게 갈 수 있는 문구를 만드는 문장을 정규식으로 모은다.
  - TypeScript: `throw new <X>Error(...)`, `new McpError(ErrorCode.<C>, ...)`, `isError: true`가 있는 반환문 가까이의 `text:` 값.
  - Python: `raise <X>(...)`, `McpError(...)`, `TextContent(..., text=...)` 가운데 문구가 "Error"나 "Failed"로 시작하는 것.
- 단위는 서로 다른 문구 틀(template)이다. 변수 자리는 `{x}`로 바꾼다. 같은 서버에서 같은 틀이 여러 번 나오면 하나로 센다.
- 문구에 글자가 거의 없고 잡은 예외를 그대로 넘기는 틀(예: `${error.message}`, `str(e)`, `Error: {x}`)은 **그대로 전달**로 따로 센다. 이때 실제 문구는 바탕 라이브러리나 운영체제가 정한다.

## 분류 규칙(대소문자 무시, 위에서부터 먼저 맞는 것)

1. **원인 명시(explained):** 문구가 바깥 원인을 말한다. 단서: `not found`, `no such`, `does not exist`, `doesn't exist`, `ENOENT`, `permission`, `denied`, `forbidden`, `unauthori`, `authenticat`, `timeout`, `timed out`, `rate limit`, `too many requests`, `network`, `connection`, `ECONN`, `unavailable`, `status`, `HTTP`, `API error`, `quota`, `outside allowed`, `not allowed`.
2. **호출 탓(call-blaming):** 문구가 요청이나 인자를 탓한다. 단서: `invalid`, `missing`, `required`, `must`, `unknown tool`, `unknown command`, `unknown action`, `not supported`, `unsupported`, `expected`, `validation`, `malformed`, `cannot be empty`, `too long`, `exceeds`, `out of range`, `parse`.
3. **원인 없음(unexplained):** 위 단서가 없다(예: `Failed to create issue`, `Internal error`, `Unknown error`).
4. **그대로 전달(passthrough):** 위 정의.

## 보고(모두 기술 통계, 검정 없음)

- 서버별·전체의 네 분류 비율. 서버마다 무게를 같게 둔 평균과, 틀 전체를 합친 비율을 함께 낸다.
- 오류가 모델에게 가는 길: 서버가 잡아서 문구로 돌려주는지(`isError` 결과), SDK로 던져 JSON-RPC 오류가 되는지. 서버마다 손으로 읽어 적는다.
- 측정 점검: 연구자(AI)가 무작위 40개 틀을 규칙을 보지 않고 다시 분류해 일치율을 낸다. 규칙 판정이 맞는지 보는 점검이며, 사람 점검이 아니다.
- 앞선 실제 서버 실험(FileSystem, Git, SQLite)에서 서버가 스스로 낸 오류 문구도 같은 규칙으로 분류해 함께 적는다.

## 해석 규칙(미리 정함)

- 원인 없음 + 호출 탓 + 그대로 전달이 절반을 넘으면: "실제 서버 코드의 오류 문구 대부분은 재활성화를 많이 일으킨 종류이거나 바탕 예외를 그대로 넘긴다"로 쓴다.
- 원인 명시가 절반을 넘으면: "실제 서버 코드의 오류는 대부분 원인을 밝힌다. 재활성화를 많이 일으킨 종류는 일부다"로 쓴다.
- 어느 쪽이든 문구의 **빈도**(실행 중 얼마나 자주 나오는가)는 이 조사로 알 수 없다고 함께 쓴다.

## 한계(미리 밝힘)

- 정규식 수집은 일부 문구를 놓치거나 오류가 아닌 문구를 섞을 수 있다. 수집한 틀 전체를 파일로 남긴다.
- 22개 서버, 한 시점의 코드다. 클라이언트가 감싸는 방식(S4)은 따로 다뤘다.
