# 창을 띄우지 않는 작업 런타임

Windows에서 사용자 프로필을 별도 폴더로 복사하고, 게임 창·콘솔 창을 표시하지 않는 Minecraft 작업 프로세스를 실행합니다. 봇 조작, Flashback 녹화, 리플레이 분석, 카메라 적용과 MP4 출력은 기존 CLI/Python 도구를 그대로 사용합니다. 기본 경로는 숨김 클라이언트의 내장 Carpet 서버이며, 기존 전용 Carpet 서버 연결용 `--server-dir` 계약도 유지합니다. 전용 서버 자동 설치나 온라인 서버 인증은 이 런타임이 수행하지 않습니다.

## 설치와 실행

Python wheel에는 지원하는 Minecraft 버전별 클라이언트 브리지와 Carpet 브리지, 그리고 버전과 무관한 시작 단계 보호 JAR이 들어 있습니다. Minecraft·Flashback·Carpet 자체는 번들하지 않습니다. 사용자가 고른 Modrinth 프로필이나 공식 런처 폴더에 이미 설치된 Minecraft 라이브러리·애셋과 Java를 그대로 사용합니다. Minecraft 버전은 해당 설치의 마지막 Fabric 실행 로그에서 알아내고, 알 수 없으면 `--minecraft-version`으로 지정합니다. Fabric이 없으면 `--install-fabric`이 Fabric Loader를 작업 인스턴스 전용으로 받아 둡니다(런처는 바꾸지 않음).

```powershell
python -m flashback_agent runtime sources
python -m flashback_agent runtime prepare --source "$env:APPDATA\ModrinthApp\profiles\내 프로필"
python -m flashback_agent runtime start
python -m flashback_agent runtime status

python -m flashback_agent call record_status
# 이후 world_open / Carpet / 녹화 / preview / render 명령도 이 작업 인스턴스를 기본으로 사용

python -m flashback_agent runtime stop
```

`prepare`의 작업 인스턴스 기본 위치는 `%LOCALAPPDATA%\FlashbackClips\worker`이며, 성공하면 이후 명령의 기본값이 됩니다. 다른 위치는 `--instance`로 지정합니다. `prepare`는 새 폴더만 허용합니다. `mods`, `config`, `resourcepacks`, `shaderpacks`, `datapacks`를 복사하고 새 폴더에서만 브리지를 갱신합니다. 원본 프로필의 모드·설정·월드는 바꾸지 않습니다. 기본적으로 월드는 복사하지 않으며 `--save 저장폴더명`을 명시하면 종료된 저장본 하나를 복사합니다. 애셋·라이브러리는 기존 설치를 읽고, 로그·리플레이·캐시·작업용 네이티브 추출물은 새 폴더에 씁니다. 인증 저장소를 읽지 않으며 별도 로컬 오프라인 관찰자 `FlashbackAgent`로 실행합니다. 게임 파일은 사용자의 런처가 이미 받아 둔 것을 씁니다.

Java는 해당 버전이 요구하는 런타임을 런처 폴더에서 찾습니다. 찾지 못하면 `--java`로 `javaw.exe` 경로를 지정합니다. Modrinth 메타데이터가 프로필 옆에 없으면 `--meta-dir`, 공식 런처에서 게임 폴더를 따로 지정했다면 `--minecraft-dir`를 씁니다. 서버 인증이 필요한 온라인 접속은 지원한다고 가정하지 마세요.

## 방해를 막는 방식

- Win32 `CreateProcessW`의 `lpDesktop`으로 사용자 입력 데스크톱과 다른 비표시 데스크톱에서 실행합니다. 자식 프로세스도 이를 상속하므로 별도 Java 업데이트 대화상자가 사용자 화면에 나타나는 경로를 막습니다. 사용자 데스크톱을 전환하는 `SwitchDesktop`은 호출하지 않습니다. Essential의 자동 업데이트 프롬프트는 작업 프로세스의 JVM 옵션으로만 비활성화합니다.
- Java `premain` 보호 장치가 Fabric과 모드보다 먼저 설치됩니다. GLFW 창 생성은 숨김·비포커스·일반 창으로 강제하고, 이후 표시·포커스·작업표시줄 주의 요청·복원·최대화·전체화면 전환·커서 이동/획득 호출을 차단합니다. 표시 후 다시 숨기는 방식이 아닙니다.
- Java AWT는 headless로 설정하며 TinyFileDialogs의 대화상자는 로그에 남는 오류로 바꿉니다. 숨김 모드가 실패해도 보이는 런처나 게임으로 재시도하지 않습니다.
- 클라이언트 비활성으로 자동 일시정지하지 않고, AFK로 틱 처리가 과도하게 느려지지 않게 합니다. 일반 실행은 기본 30 FPS, 메모리 상한 4 GiB, 낮은 프로세스 우선순위, JVM 인식 CPU 4개입니다. `start --fps 20..120 --memory-mb 1024..16384`로 변경할 수 있습니다. 출력 MP4의 FPS는 `render --fps`로 독립 지정합니다.
- OpenAL의 `null` 재생 장치로 PC 스피커 출력을 막습니다. Flashback의 오프라인 오디오 렌더는 별도 loopback 경로를 사용합니다. 원본 프로필의 음량은 변경하지 않습니다.
- 시작 완료는 해당 실행 ID의 브리지가 준비되고 GLFW의 표시·포커스·전체화면 상태가 모두 꺼졌을 때만 반환합니다. `status`는 Windows에서 해당 PID의 표시 창과 전경 여부도 확인합니다.
- PID와 프로세스 생성 시간을 함께 기록하고, 종료 도구는 실행 ID가 일치하는 작업 프로세스만 종료합니다. 활성 녹화·출력·월드 로드 중에는 종료를 거부합니다. 정상 종료는 월드 저장을 기다리며 시간 초과 시 강제 종료하지 않습니다.

보호 범위는 이 런타임으로 시작한 프로세스와 데스크톱을 상속하는 자식입니다. Modrinth에서 직접 시작한 개인 게임은 정상적으로 창을 표시합니다. PC 절전/로그아웃 중 작업 지속이나 GPU 자원 사용량 0을 뜻하지 않습니다. 명시적으로 다른 데스크톱을 열거나 기존 외부 앱에 메시지를 보내는 임의의 제3자 코드를 막는 보안 샌드박스는 아닙니다.

## 상태와 복구

인스턴스의 `.background/instance.json`은 설치 정보, `process.json`은 실행 ID·PID·생성 시각·로그 위치를 보관합니다. 실행마다 별도 `.log`와 `.args`를 만듭니다. 보호 JAR/브리지 체크섬이 달라지면 시작하지 않습니다. `start` 시간 초과는 프로세스 종료가 아니므로 `status`와 로그를 먼저 확인하세요. 중복 `start`는 거부합니다.

`record_status`의 `background`에는 `enabled`, `guard`, `visible`, `focused`, `fullscreen`, `desktopAudio`, `backgroundFps`, `launchId`, `pid`가 있습니다. `screen`은 숨겨진 로딩/오류 화면의 클래스 이름입니다. 레지스트리 변경 등의 Minecraft 확인 화면은 자동 승인하지 않으며 창을 띄워 해결하지도 않습니다. 로그와 상태를 근거로 원인을 해결해야 합니다.

개발 소스에서 wheel을 만들 때 먼저 `gradlew.bat build`를 실행하고 `python scripts/stage_bridges.py`로 `flashback-agent`, `carpet-agent`, `flashback-background` 세 JAR을 `flashback_agent/bin`에 복사한 다음 wheel을 빌드합니다. 네이티브 보호 검증은 `tests/live_background_guard.py`, 실제 봇·녹화·오디오 MP4·정상 종료 검증은 `tests/live_background.py`입니다. 후자는 준비된 작업 인스턴스와 폐기 가능한 `carpet-agent-test` 저장본 전용입니다.
