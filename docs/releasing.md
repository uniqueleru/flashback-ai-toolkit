# 배포 안내 (관리자용)

PyPI 패키지 `flashback-ai-toolkit`은 GitHub Actions의 `Build` 워크플로가 `v*` 태그에서 빌드하고 게시합니다.

## 버전 정보가 있는 곳

브리지가 대상으로 하는 Minecraft 버전과 Flashback·Fabric API·Carpet·Java 버전은 `gradle.properties` 한 곳에만 있습니다. Python과 Java 코드는 버전을 직접 적지 않습니다.

- `gradlew build`는 이 값으로 브리지를 컴파일하고 `fabric.mod.json`의 의존성을 채웁니다.
- `scripts/stage_bridges.py`는 빌드된 JAR을 `flashback_agent/bin/<minecraft>/`에 복사하고 `bridge.json`을 만듭니다. Flashback·Fabric API·Carpet의 정확한 파일과 sha512는 이때 Modrinth API에서 가져옵니다.
- 실행 시 툴킷은 사용자 설치의 Minecraft 버전에 맞는 `bin/<버전>/bridge.json`을 고릅니다. Flashback(`exact`)은 항상 그 빌드로 바꾸고, Fabric API·Carpet(`minimum`)은 사용자 설치에 같거나 더 새 버전이 있으면 그대로 둡니다.

## 새 Minecraft 버전 추가

1. `gradle.properties`의 `minecraft_version`, `java_version`, `loader_version`, `fabric_api_version`, `flashback_version`, `flashback_modrinth`(Modrinth 버전 ID), `carpet_modrinth`를 새 버전에 맞게 바꿉니다.
2. Flashback·Minecraft 내부 API 변경에 맞춰 브리지 코드(믹스인 포함)를 고치고 `gradlew build`로 빌드·테스트합니다.
3. `python scripts/stage_bridges.py`를 실행합니다.
4. 실제 리플레이로 `tests/live_general.py`, 봇과 녹화는 `tests/live_carpet.py`로 확인합니다.

현재 빌드는 한 번에 한 버전만 만듭니다. 여러 버전을 함께 배포하려면 버전별로 빌드해서 `stage_bridges.py`를 각각 실행해 `bin/` 아래에 폴더를 모은 뒤 wheel을 만들면 됩니다. 툴킷은 들어 있는 폴더를 모두 지원 버전으로 인식합니다.

## PyPI 신뢰할 수 있는 게시자 (처음 한 번)

API 토큰을 저장소에 두지 않고 GitHub OIDC로 게시합니다.

1. pypi.org → Account settings → Publishing → 새 대기 게시자(pending publisher) 추가.
2. PyPI Project Name `flashback-ai-toolkit`, Owner `uniqueleru`, Repository name `flashback-ai-toolkit`, Workflow name `build.yml`, Environment name `pypi`.
3. GitHub 저장소 Settings → Environments에 `pypi` 환경을 만듭니다. 게시 전에 직접 승인하려면 Required reviewers에 본인을 추가합니다.

## 릴리스

1. 툴킷 버전을 올립니다: `pyproject.toml`, `build.gradle`, `flashback_agent/runtime.py`의 `VERSION`. 세 값이 다르면 `tests/test_packaging.py`가 실패합니다.
2. 로컬에서 확인합니다.

   ```powershell
   .\gradlew.bat build
   python scripts/stage_bridges.py
   python -m unittest discover -s tests
   uvx --from build pyproject-build
   .\install.ps1 -Package .\dist\flashback_ai_toolkit-0.4.0-py3-none-any.whl
   ```

3. 커밋하고 태그를 푸시합니다: `git tag v0.4.0`, `git push origin v0.4.0`.
4. Actions의 `Build`가 Gradle 빌드·Java 테스트 → 브리지 스테이징 → Python 테스트 → wheel/sdist 빌드 → 설치 확인 → PyPI 게시 순서로 진행합니다. 태그와 패키지 버전이 다르면 시작 단계에서 멈춥니다.

main 브랜치 푸시와 PR에서는 게시 없이 빌드와 테스트만 실행합니다.
