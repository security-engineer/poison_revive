# 평가자에게 보내는 법 (2026-10-11)

> **현황 (2026-10-14 추가). 아래 안내는 끝난 일이다.**
> - 평가는 2026-10-14에 끝났다. 평가자 A(제1저자) 한 명의 판정만 쓴다(사용자 결정, `score_results_A_only/NOTE_KO.md`).
> - 돌아온 파일은 `returned/`에 있다. B 파일은 A와 판정·질문 2 답·메모까지 300개가 모두 같아서 독립된 평가로 쓸 수 없었다.
> - 채점 결과는 `score_results_A_only/`에 있다(`NOTE_KO.md` 먼저). `score.py`를 고치지 않고 A 파일을 두 번 넣어 돌렸다.
> - `signature_review.xlsx`(판정 규칙 검토)는 돌아오지 않았다(`returned/`에는 항목 판정 파일 두 개뿐이다).
> - 100개 판(`../human_validation_v1_100/`)은 쓰지 않았다.
> - 다음에 묶음을 만들 때는 "근거 위치" 선택지 "본문 글"(`GUIDE_KO.md` 5.4·6절, xlsx I열)을 "다음 응답의 글"로 바꾼다. 안내서 3절은 같은 칸을 "다음 응답: 글"이라고 부른다.
> - 자세한 기록: `prereg/DEVIATIONS_AND_TIMELINE_KO.md` §2.31.

평가자는 두 명이다. 평가자 A는 연구자 본인이고, 평가자 B는 동료 1명이다.

| 받는 사람 | 보낼 것 | 들어 있는 파일 |
|---|---|---|
| 평가자 A (본인) | `to_annotator_A.zip` 또는 `to_annotator_A/` 폴더 | `annotate_A.xlsx`, `annotate_items.html`, `GUIDE_KO.md` |
| 평가자 B (동료) | `to_annotator_B.zip` 또는 `to_annotator_B/` 폴더 | `annotate_B.xlsx`, `annotate_items.html`, `GUIDE_KO.md` |

- 폴더째(`human_validation_v1/`) 넘기지 않는다. `KEY_DO_NOT_OPEN.json`, `README_KO.md`, `SAMPLING_MANIFEST.json`은 평가가 끝날 때까지 평가자가 보면 안 된다.
- 평가자 A가 연구자 본인이므로, 평가를 마칠 때까지 정답표와 README를 열지 않는다. 항목에서는 조건, 모델, 판정 규칙이 가려져 있다.
- 두 사람은 끝날 때까지 서로 항목을 이야기하지 않고, AI 도구에 판정을 묻지 않는다.
- 한 사람당 7~11시간이 걸린다. 다 채운 `annotate_A.xlsx`, `annotate_B.xlsx`를 이 폴더에 다시 넣으면 `score.py`로 채점한다.
- 두 사람의 항목 판정이 모두 끝난 뒤에 `signature_review.xlsx`(판정 규칙 검토, 선택)를 보낸다.
