# Flashback Clips

[English](README.md) | **한국어**

Flashback 리플레이를 조사하고, Agent가 설계한 카메라와 컷 편집을 실제 MP4로 실행하는 CLI·Python 라이브러리·Fabric 브리지·Agent Skill입니다. **촬영 의도와 연출은 Agent가 결정합니다.** 플레이어 추적은 선택 가능한 기존 도구 하나이며 기본 동작이 아닙니다.

Agent는 요청에 따라 리플레이/엔티티 정보를 읽고, 임의의 월드 좌표 카메라 계획을 작성하고, 프리뷰를 검토·수정한 뒤 단일 클립이나 여러 샷을 출력할 수 있습니다. 피사체 없는 풍경, 정지 화면 구도의 샷, 이동/회전/줌, 엔티티 데이터를 활용한 촬영 등을 같은 도구로 표현합니다. 도구 자체에 LLM이나 자동 하이라이트 판별기는 없습니다.

Carpet 봇 도구와 Flashback 녹화 도구로 에이전트가 관측 결과를 바탕으로 행동을 조합하고, 녹화본을 만든 다음 별도로 카메라를 연출할 수 있습니다. `python -m flashback_agent tools`에서 20개 도구의 설명·JSON 스키마를 조회합니다. CLI·Python·선택적 MCP stdio가 같은 도구를 호출합니다. 의미와 한계는 [Carpet 도구 문서](docs/carpet-tools.md)에 있습니다.

**백그라운드에서 실행됩니다.** Windows 비표시 데스크톱과 창 생성 전에 걸리는 보호 장치를 씁니다. 사용자가 고른 Minecraft 설치를 별도 작업 인스턴스로 복사해 실행하고, 게임·자식 대화상자·콘솔 창 표시, 포커스와 마우스 획득, PC 스피커 출력을 막습니다. 자세한 내용은 [숨김 실행 문서](docs/background-runtime.md)를 참조하세요. Agent Skill은 이 실행 경로를 기본으로 사용하며, 장면과 카메라 연출은 계속 요청에 따라 자유롭게 결정합니다.

## 설치

Windows 10/11 x64(숨김 실행 런타임은 현재 Windows 전용)와 **Modrinth 앱 또는 공식 Minecraft 런처**로 설치한 Minecraft가 필요합니다.

```powershell
uv tool install flashback-ai-toolkit
flashback-clips setup
```

uv가 없다면 `winget install astral-sh.uv`로 설치하거나, 이 저장소의 `install.cmd`를 더블클릭하세요. uv 설치와 위 두 명령을 대신 실행합니다. Python 3.11+는 uv가 직접 준비하며 시스템 Python은 바꾸지 않습니다. `setup`은 Codex / Claude Code용 스킬을 설치하고 FFmpeg를 찾습니다(없으면 WinGet으로 설치). Minecraft에는 손대지 않습니다.

### 처음 쓸 때: Minecraft 설치를 직접 고릅니다

에이전트에게 처음 영상을 맡기면, 에이전트가 함께 작업 인스턴스를 준비합니다.

1. 에이전트가 `flashback-clips runtime sources`로 찾은 Modrinth 프로필과 공식 런처 폴더를 보여 줍니다. 각 항목에는 마지막으로 실행한 Minecraft·Fabric 버전이 함께 나옵니다. 사용자가 하나를 고르거나 다른 경로를 알려 주며, 에이전트가 대신 고르지 않습니다.
2. `flashback-clips runtime prepare --source "<경로>"`가 그 설치의 모드·설정·리소스팩·셰이더팩을 `%LOCALAPPDATA%\FlashbackClips\worker`의 별도 작업 인스턴스로 복사합니다. 원래 설치는 수정하지 않습니다. Flashback은 항상 브리지가 컴파일된 정확한 빌드를 쓰고, Fabric API와 Carpet은 설치에 브리지 버전 이상이 있으면 그대로 둡니다. 없거나 더 오래된 것만 받아 해시를 검증합니다.
3. **그 설치에 Fabric이 없다면** 에이전트가 알려 주고 `--install-fabric`으로 다시 실행합니다. Fabric Loader를 작업 인스턴스 전용으로 받으며 런처는 바꾸지 않습니다.

Minecraft 버전은 툴킷에 고정하지 않고 설치에서 알아냅니다. 브리지 빌드가 있는 버전이면 동작하며, 목록은 `flashback-clips capabilities`에서 볼 수 있고 그 밖의 버전은 지원 버전을 안내합니다. 작업 인스턴스는 런처가 이미 받아 둔 게임 파일을 쓰므로, 쓰려는 버전을 런처에서 한 번 실행해 두세요. 별도 로컬 오프라인 관찰자로 실행하며 계정 토큰은 읽지 않습니다.

`flashback-clips doctor`가 각 항목의 상태를 JSON으로 보여 줍니다. 옵션과 문제 해결은 [설치 안내](docs/install.md)를 참고하세요.

### 수동 설치와 개발 설치

1. `gradlew.bat build`로 빌드합니다. 대상 Minecraft 버전과 Flashback·Fabric API·Carpet 버전은 `gradle.properties`에 있습니다. 이어서 `python scripts/stage_bridges.py`가 브리지를 `flashback_agent/bin/<minecraft>/`에 복사하고 `bridge.json`을 만듭니다.
2. CLI는 `uv tool install flashback-ai-toolkit`, `python -m pip install flashback-ai-toolkit`, 또는 소스에서 `python -m pip install -e .`로 설치합니다. Python 런타임 의존성은 없습니다.
3. 샷 결합과 검토 프레임 추출에는 FFmpeg와 ffprobe를 PATH에 준비합니다.
4. `setup`을 쓰지 않는다면 `.agents/skills/flashback-clips`를 Agent가 검색하는 Skill 폴더에 설치합니다. 전역 설치 위치는 Codex가 `$CODEX_HOME/skills/flashback-clips`(기본 `~/.codex`), Claude Code가 `~/.claude/skills/flashback-clips`입니다.

수동으로 보이는 게임을 사용할 때만 일반 런처를 사용합니다. 리플레이 작업은 타이틀 화면 또는 리플레이에서 실행하며 실시간 월드/서버에서는 거부합니다. 봇·녹화 도구는 실시간 월드에서 실행합니다. 설치한 뒤 어느 디렉터리에서든 `flashback-clips`를 사용할 수 있고, `python -m flashback_agent`도 동일하며 `mc-broll`은 호환 별칭입니다.

## 도구 사용

```powershell
python -m flashback_agent capabilities
python -m flashback_agent doctor
python -m flashback_agent inspect 'D:\replays\session.zip'
python -m flashback_agent sample --replay 'D:\replays\session.zip' --range 03:00-03:05 --step 10
python -m flashback_agent validate-plan 'D:\clips\camera.json' --range 03:00-03:05
python -m flashback_agent preview --replay 'D:\replays\session.zip' --range 03:00-03:05 --plan 'D:\clips\camera.json' --output 'D:\clips\preview.mp4'
python -m flashback_agent review 'D:\clips\preview.mp4' --output-dir 'D:\clips\preview-frames' --every 0.25
python -m flashback_agent render --replay 'D:\replays\session.zip' --range 03:00-03:05 --plan 'D:\clips\camera.json' --output 'D:\clips\final.mp4'
```

경로와 좌표는 자신의 리플레이에 맞게 지정합니다. 게임 명령은 `runtime prepare`로 만든 작업 인스턴스를 기본으로 쓰며, 다른 곳을 쓰려면 `--game-dir`로 지정합니다. 기존 출력은 덮어쓰지 않습니다. stdout은 JSON, stderr는 진행 상태입니다. 게임 작업의 `--submit-only`는 job ID를 즉시 반환합니다.

| 도구 | 역할 |
| --- | --- |
| `inspect`, `capabilities`, `doctor` | 메타데이터·도구 범위·실행 환경 확인 |
| `players`, `sample` | 기록된 플레이어 탐색, 엔티티 위치·방향·차원 샘플링 |
| `validate-plan`, `validate-edit` | 카메라와 전체 편집 계획 사전 검증 |
| `preview`, `render` | 명시적 카메라 계획으로 프리뷰/본 렌더 |
| `sequence` | 여러 리플레이/구간의 샷을 지정한 순서로 렌더·결합 |
| `assemble`, `review` | 출력 클립 컷 연결, 미디어 정보·검토용 프레임 추출 |
| `status`, `wait`, `cancel` | 작업 조회·대기·취소 |

`preview` 기본값은 640×360/24 FPS, `render`는 1920×1080/60 FPS입니다. 가로·세로 각각 64~4096의 짝수, FPS 24/30/60을 지원하며 세로 영상도 가능합니다. `--audio`를 주면 리플레이 오디오를 포함하고 기본은 무음입니다.

## 자유 카메라와 편집 계획

`camera.json` 예제는 원본 180~185초 구간의 고정 월드 카메라입니다. 실제 장면을 조사해 위치와 시선을 정해야 합니다.

```json
{
  "version": 1,
  "speed": 1,
  "camera": [
    {"tick": 3600, "position": [10, 80, -10], "lookAt": [0, 70, 0], "fov": 55}
  ]
}
```

키 한 개는 전체 구간에서 고정 카메라입니다. 여러 키는 구간을 덮는 원본 절대 tick에 배치하며 위치, yaw/pitch 또는 lookAt, roll, FOV, 보간을 지정합니다. 속도는 샷별 0.1~8배입니다. `lookAt`은 각 키의 방향으로 변환되며 지속적인 타깃 바인딩이 아닙니다. 카메라는 지정한 계획을 실행하고 임의로 추적·흔들림·안정화·충돌 보정을 추가하지 않습니다.

전체 스키마와 편집 예제는 [카메라/편집 계획](.agents/skills/flashback-clips/references/plans.md), 명령별 동작과 한계는 [도구 참조](.agents/skills/flashback-clips/references/tools.md)에 있습니다.

```powershell
python -m flashback_agent validate-edit edit.json
python -m flashback_agent sequence --edit edit.json --output montage.mp4 --work-dir render-work
# 대기를 중단했다면 같은 계획과 경로로 이어서 실행합니다.
python -m flashback_agent sequence --edit edit.json --output montage.mp4 --work-dir render-work --resume
```

`sequence`는 모든 입력을 사전 검증하고, 지정 순서대로 샷을 렌더하며 job ID를 체크포인트에 보존합니다. 원본 시간순으로 강제 정렬하지 않습니다. `assemble`은 동일 해상도·FPS·오디오 구성의 클립을 H.264/AAC로 재인코딩해 컷으로 연결합니다.

Python에서도 동일한 기능을 사용합니다.

```python
from flashback_agent import bridge_health, submit_job, wait_job, validate_plan
from flashback_agent.sequence import render_sequence

bridge_health(profile)
plan = validate_plan('camera.json', 3600, 3700)
job = submit_job(profile, replay, '03:00-03:05', output='final.mp4', plan=plan, fps=30)
result = wait_job(job, timeout=1800)
if result['state'] != 'completed':
    raise RuntimeError(result.get('error', result['state']))
```

기존 자동 추적은 `render ... --style dynamic-follow --target PlayerName`을 명시한 경우에만 CLI에서 선택됩니다. Python의 기존 `target` API도 호환 유지합니다. 명시적 카메라 계획에는 추적 대상/거리 옵션을 함께 넣을 수 없습니다.

## Agent Skill

`flashback-clips` 스킬(Codex는 `$flashback-clips`, Claude Code는 `/flashback-clips`)의 지침은 요청에 맞게 조사·촬영·편집 도구를 선택하도록 구성했습니다. 특정 피사체, 샷 스타일, 움직임, 영상 목적이나 일정한 제작 절차를 강제하지 않습니다. 예전 추적 프리셋으로 요청을 축소하지 않고, 구현되지 않은 요구는 구체적인 한계로 설명하거나 적절한 다른 편집 도구와 조합합니다.

Skill에 LLM API 키는 필요하지 않습니다. 호출한 Agent가 자연어 해석과 장면 판단을 맡습니다. 처음 쓸 때는 스킬이 위의 방식으로 어떤 Minecraft 설치를 쓸지 사용자에게 묻게 합니다. 도구가 생성하는 샘플은 의미 분석 결과가 아니며, `review`의 정지 프레임만으로 움직임 품질을 증명할 수는 없습니다.

## 실행과 한계

- 실제 Minecraft 클라이언트와 그래픽 드라이버, 녹화에 필요한 모드/레지스트리가 필요합니다. 순수 headless ZIP 변환기가 아닙니다.
- 범용성은 Agent의 연출과 도구 조합에 있습니다. Flashback의 모든 UI 기능을 CLI로 노출하지는 않습니다. 샷당 한 차원, 고정 순방향 속도를 지원합니다. 역재생·정지·속도 곡선·전환 효과는 현재 내장되지 않았습니다.
- 엔티티 샘플은 그 시점에 로드된 녹화 엔티티입니다. 카메라 시야나 전체 서버 상태, 흥미로운 사건을 자동 판정하지 않습니다. 미기록 청크와 차원 이동은 적절한 구간 분리와 검토가 필요합니다.
- 자유 카메라의 지오메트리 통과나 피사체 가림을 자동 수정하지 않습니다. 필요한 검토와 수정은 Agent가 요청에 맞춰 결정합니다. 기존 추적 도구의 간단한 충돌 처리도 모든 프레임을 보장하지 않습니다.
- 리소스팩·셰이더·모드 외형은 실행 프로필에 따릅니다. 변속 오디오는 네이티브 리플레이 재생에 따르며 고품질 오디오 타임스트레치 기능은 아닙니다.
- 원본 리플레이와 저장된 편집 상태를 수정하지 않습니다. 작업별 카메라 계획/편집 상태를 따로 저장합니다. 완료된 프레임과 파일을 확인한 뒤 출력하며 실패·취소 시 부분 파일은 완료 MP4로 게시하지 않습니다.
- Ctrl+C나 대기 타임아웃은 작업을 취소하지 않습니다. job ID로 조회/대기/취소하십시오. 브리지 재시작 중 끊긴 작업은 실패로 남기고 자동 재실행하지 않습니다.

상세 파일 프로토콜은 [docs/protocol.md](docs/protocol.md)에 있습니다.

## 검증

자동 테스트는 아래 Python·Java 명령으로 실행합니다. 설치기 테스트 일부는 브리지 JAR이 필요하므로 Gradle 빌드 뒤 `python scripts/stage_bridges.py`를 실행합니다. 배포는 GitHub Actions가 빌드하고 게시합니다([배포 안내](docs/releasing.md)). Carpet 통합 검증은 별도 복사본 월드 `run/saves/carpet-agent-test`에서 `tests/live_carpet.py --work-dir NEW_DIRECTORY`로 실행합니다. 이 테스트는 해당 테스트 월드 이름을 확인한 후 무대를 만들고 봇 두 명을 조작하므로 실제 사용 중인 월드로 경로를 바꾸어 실행하지 마십시오. 봇 상태·시간 제한·잘못된 대상/녹화 ID 거부·직접 녹화·리플레이 엔티티 조회·명시적 카메라 MP4 출력을 검증합니다. 녹화자의 관전자 모드와 배우의 일반 모드가 서로 섞이지 않는지도 검사합니다.

```powershell
.\gradlew.bat build
python scripts/stage_bridges.py
python -m unittest discover -s tests -v
# 별도 개발 프로필. 녹화에 필요한 추가 모드는 run/mods에 준비합니다.
.\gradlew.bat runClient
$env:PYTHONPATH = (Get-Location).Path
python tests/live_general.py --game-dir run --replay 'D:\replays\test.zip' --output 'D:\clips\general-test.mp4' --work-dir 'work\general-test-new'
```

실제 통합 테스트에는 9초 이상이며 플레이어가 포함된 호환 리플레이와 ffprobe/FFmpeg가 필요합니다. 해당 테스트의 플레이어는 장면 좌표를 찾는 기준으로만 사용하고 렌더 요청에는 타깃을 전달하지 않습니다.

0.2.0에서 Python 테스트 11개와 Java 테스트 12개를 통과했습니다. 제공된 11.15초 리플레이로 엔티티 쿼리 → 고정 월드 카메라 → 직접 작성한 3키 이동 카메라/2배속 → 두 샷 결합을 실제 실행하여 640×360/24 FPS, 4초/96프레임 MP4를 확인했습니다. 별도 CLI 프리뷰는 타깃 없이 1초/24프레임과 AAC 오디오를 출력했습니다. 대표 프레임으로 구도를 확인했으며 전체 모션 품질 평가를 수행했다는 뜻은 아닙니다.

실영상 검증 환경은 Flashback·Fabric API·Lithostitched를 포함한 별도 개발 프로필입니다. 셰이더를 포함한 대형 모드팩 조합과 장시간 리플레이는 미검증입니다. 기존 0.1.0의 추적 데모/검증 보고서는 이전 버전 자료이며 범용 기능의 검증 근거로 혼용하지 않습니다.

## 라이선스

[MIT](LICENSE). Minecraft, Flashback, Carpet, Fabric은 각자의 라이선스를 가진 별도 프로젝트이며 이 저장소와 배포 패키지에 포함하지 않습니다. 이 프로젝트는 Minecraft 공식 제품이 아니며 Mojang 또는 Microsoft의 승인을 받거나 이들과 관련이 있지 않습니다.
