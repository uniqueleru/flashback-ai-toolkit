# 설치 안내

관리자 권한 없이 현재 사용자용으로 설치합니다. 명령 출력은 영어이며, 경로에는 한글과 공백을 사용할 수 있습니다.

## 준비할 것

- Windows 10/11 x64와 인터넷 연결. 숨김 실행 런타임은 현재 Windows 전용입니다.
- **Modrinth 앱 또는 공식 Minecraft 런처**로 설치한 Minecraft. 쓰려는 버전을 런처에서 한 번 실행해 두세요. 게임 파일·라이브러리·애셋·Java가 이때 준비됩니다.
- 지원 Minecraft 버전은 툴킷에 들어 있는 브리지 빌드에 따라 정해집니다. `flashback-clips capabilities`의 `bridges`에서 확인할 수 있습니다.

Flashback, Fabric API, Carpet은 직접 넣지 않아도 됩니다. 작업 인스턴스를 만들 때 **작업 인스턴스에만** 넣습니다. Flashback은 항상 브리지에 맞는 정확한 빌드로 바꾸고, Fabric API와 Carpet은 설치에 브리지 버전 이상이 있으면 그대로 둡니다(다른 모드가 더 새 버전을 요구할 수 있기 때문). 원래 설치의 모드와 월드는 수정하지 않습니다. 다만 원래 설치의 다른 모드·설정·리소스팩·셰이더팩은 복사되므로, 이들이 해당 버전과 호환돼야 합니다.

## 설치

```powershell
uv tool install flashback-ai-toolkit
flashback-clips setup
```

uv가 없다면 `winget install astral-sh.uv`로 설치하거나, 저장소의 `install.cmd`를 더블클릭하세요. `install.cmd`는 `install.ps1`을 실행해 uv를 설치하고(WinGet), `uv tool install`과 `flashback-clips setup`을 이어서 실행합니다. Python 3.11 이상은 uv가 필요할 때 직접 준비하며 시스템 Python을 바꾸지 않습니다. `uv tool update-shell`로 `flashback-clips` 명령 폴더를 사용자 PATH에 추가합니다.

`setup`은 다음만 합니다. Minecraft에는 손대지 않습니다.

1. FFmpeg와 ffprobe를 확인하고, 없으면 WinGet의 `Gyan.FFmpeg`를 현재 사용자용으로 설치합니다.
2. 에이전트 스킬을 설치합니다. 기본값(`--agent auto`)은 이미 설정된 에이전트를 찾아 Codex는 `$CODEX_HOME/skills/flashback-clips`(기본 `~/.codex`), Claude Code는 `$CLAUDE_CONFIG_DIR/skills/flashback-clips`(기본 `~/.claude`)에 설치합니다. 둘 다 없으면 두 곳 모두에 설치합니다. 기존 스킬은 `skills` 옆의 `skill-backups`에 먼저 백업합니다.
3. `%LOCALAPPDATA%\FlashbackClips\config.json`에 FFmpeg와 스킬 위치를 기록합니다.

| `setup` | `install.ps1` | 용도 |
| --- | --- | --- |
| `--agent` | `-Agent` | 스킬 설치 대상: `auto`(기본), `codex`, `claude`, `both` |
| `--skill-dir` | `-SkillDir` | 스킬을 설치할 정확한 `flashback-clips` 폴더; `--agent` 대신 사용 |
| `--skip-skill` | `-SkipSkill` | 에이전트 스킬 설치 생략 |
| `--no-dependency-install` | `-NoDependencyInstall` | FFmpeg(설치기는 uv 포함)가 없으면 자동 설치 대신 오류 반환 |
| | `-Package` | PyPI 대신 설치할 wheel 경로(배포 전 확인용) |
| | `-NoPathUpdate` | 사용자 PATH를 바꾸지 않음 |

WinGet 자동 설치 시 해당 패키지와 저장소 약관에 동의하는 옵션을 사용합니다. `install.cmd`는 결과를 읽을 수 있도록 마지막에 키 입력을 기다립니다. 실행 정책 우회는 해당 PowerShell 프로세스에만 적용되며 시스템 실행 정책을 변경하지 않습니다.

## 처음 쓸 때: Minecraft 설치 고르기

설치 후 에이전트(Codex / Claude Code)를 다시 열고 영상을 요청하면, 에이전트가 먼저 작업 인스턴스를 준비합니다. 직접 해도 됩니다.

```powershell
flashback-clips runtime sources
flashback-clips runtime prepare --source "G:\modrinth\profiles\내 프로필"
```

- `runtime sources`는 기본 위치와 Modrinth 앱에 지정된 데이터 폴더의 프로필, 그리고 `%APPDATA%\.minecraft`를 찾습니다. 각 항목에는 마지막으로 실행한 Minecraft·Fabric 버전과, 그 버전의 브리지 빌드가 있는지가 나옵니다. 목록에 없어도 경로를 직접 지정할 수 있습니다. Modrinth는 프로필 폴더, 공식 런처는 게임 폴더(기본 `%APPDATA%\.minecraft`)를 지정합니다.
- 에이전트는 이 목록을 보여 주고 사용자에게 고르게 합니다. 대신 고르지 않습니다.
- `runtime prepare`가 성공하면 그 작업 인스턴스가 이후 모든 명령의 기본값이 됩니다. `FLASHBACK_GAME_DIR` 환경 변수나 `--game-dir`가 있으면 그 값이 우선합니다.

| `runtime prepare` 옵션 | 용도 |
| --- | --- |
| `--source` | 사용할 Modrinth 프로필 폴더 또는 공식 런처 게임 폴더(필수) |
| `--launcher` | `auto`(기본), `modrinth`, `official` |
| `--minecraft-version` | 설치의 Fabric 실행 로그로 버전을 알 수 없을 때 지정 |
| `--install-fabric` | 그 설치에 Fabric이 없을 때 Fabric Loader를 작업 인스턴스 전용으로 받기 |
| `--instance` | 새 작업 인스턴스 폴더; 기본값은 `%LOCALAPPDATA%\FlashbackClips\worker` |
| `--meta-dir` | Modrinth `meta` 폴더가 프로필 옆에 없을 때 |
| `--minecraft-dir` | 공식 런처에서 게임 폴더를 따로 지정했을 때, 원래 `.minecraft` 폴더 |
| `--java` | 해당 버전이 요구하는 Java의 `javaw.exe`(런처 폴더에서 찾지 못할 때) |
| `--save` | 종료된 저장본 하나를 복사; 기본은 월드를 복사하지 않음 |

### 자주 보는 메시지

| 메시지 | 원인과 해결 |
| --- | --- |
| `No bridge build for Minecraft X` | 그 버전용 브리지가 아직 없습니다. 안내된 지원 버전의 설치를 고르세요. |
| `Fabric Loader ... is not installed` | `--install-fabric`을 붙여 다시 실행하면 작업 인스턴스 전용으로 받습니다. 런처는 바뀌지 않습니다. |
| `Could not tell which Minecraft version` | `--minecraft-version`으로 버전을 지정하세요. |
| `Missing library` / `game files were not found` | 그 버전을 런처에서 한 번 실행한 뒤 다시 시도하세요. |
| `Java N was not found` | 런처에서 한 번 실행하거나 `--java`로 경로를 지정하세요. |
| `mods here are for Forge/NeoForge` | Fabric 또는 바닐라 설치를 고르세요. |

## 설치 후 사용

```powershell
flashback-clips runtime start
flashback-clips doctor
flashback-clips runtime stop
```

`doctor`는 Python, 플랫폼, FFmpeg/ffprobe, 브리지 빌드, 스킬, 작업 인스턴스, 브리지 연결 상태를 JSON으로 보고합니다. 모두 통과하면 `ok: true`와 종료 코드 0입니다. 브리지 항목은 작업 인스턴스가 실행 중일 때만 통과합니다.

같은 `--source`로 `runtime prepare`를 다시 실행하면 완료된 인스턴스를 재사용합니다. 다른 설치, 바뀐 브리지/필수 모드, 준비 도중 실패한 폴더는 덮어쓰지 않으므로 `--instance`로 새 폴더를 지정하세요. 새 버전으로 올릴 때는 `uv tool upgrade flashback-ai-toolkit` 뒤 새 `--instance`로 준비합니다.

## 제거

```powershell
uv tool uninstall flashback-ai-toolkit
```

이어서 데이터 폴더 `%LOCALAPPDATA%\FlashbackClips`(작업 인스턴스·다운로드·config.json)와 설치된 스킬 폴더를 직접 지우면 됩니다. 원래 Minecraft 설치는 처음부터 수정하지 않았습니다.
