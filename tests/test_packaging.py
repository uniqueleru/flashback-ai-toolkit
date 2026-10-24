import json
from pathlib import Path
import re
import tomllib
import unittest

from flashback_agent import runtime

ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_python_and_gradle_versions_match(self):
        project = tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['project']
        gradle = re.search(r"^version = '([^']+)'", (ROOT/'build.gradle').read_text(encoding='utf-8'), re.M).group(1)
        self.assertEqual({project['version'], gradle}, {runtime.VERSION})

    def test_staged_bridge_matches_gradle_target(self):
        props = dict(line.split('=', 1) for line in (ROOT/'gradle.properties').read_text(encoding='utf-8').splitlines()
                     if '=' in line and not line.startswith('#'))
        manifest = ROOT/'flashback_agent/bin'/props['minecraft_version']/'bridge.json'
        if not manifest.is_file():
            self.skipTest('bridges not staged; run gradlew build and scripts/stage_bridges.py')
        build = json.loads(manifest.read_text(encoding='utf-8'))
        self.assertEqual((build['java'], build['fabricLoader'], build['flashback']),
                         (int(props['java_version']), props['loader_version'], props['flashback_version']))
        self.assertEqual({d['id'] for d in build['dependencies']}, {'flashback', 'fabric-api', 'carpet'})

    def test_wheel_skill_mapping_points_at_the_repository_skill(self):
        setuptools = tomllib.loads((ROOT/'pyproject.toml').read_text(encoding='utf-8'))['tool']['setuptools']
        skill = ROOT/setuptools['package-dir']['flashback_agent.skill']
        self.assertTrue((skill/'SKILL.md').is_file())
        for package in setuptools['packages']:
            if package.startswith('flashback_agent.skill.'):
                self.assertTrue((skill/package.rpartition('.')[2]).is_dir(), package)
