import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


@unittest.skipUnless(shutil.which("make"), "make is required for deployment workflow tests")
class EksDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.log = self.root / "commands.jsonl"
        self.state = self.root / "applied"
        self.makefile = Path(__file__).resolve().parents[1] / "Makefile"
        (self.root / "Makefile").symlink_to(self.makefile)
        mock = f"#!{sys.executable}\n" + '''
import json
import os
from pathlib import Path
import sys

tool = Path(sys.argv[0]).name
arguments = sys.argv[1:]
with open(os.environ["MOCK_LOG"], "a") as stream:
    stream.write(json.dumps([tool, arguments]) + "\\n")
if tool == "terraform":
    if "apply" in arguments:
        Path(os.environ["MOCK_STATE"]).touch()
    if "output" in arguments:
        if not Path(os.environ["MOCK_STATE"]).exists():
            raise SystemExit("Terraform outputs were read before apply")
        outputs = {
            "namespace": "nebraska-app",
            "cluster_name": "nebraska-eks",
            "ecr_repository_url": "123456789012.dkr.ecr.us-east-1.amazonaws.com/nebraska-eks-app",
            "image_tag": "test-tag",
            "build_local_image": os.environ.get("MOCK_BUILD_LOCAL", "true"),
            "helm_values": "{}",
            "app_url": "http://example.test",
        }
        print(outputs[arguments[-1]])
elif tool == "aws" and arguments[:2] == ["ecr", "get-login-password"]:
    print("test-only-placeholder")
elif tool == "docker":
    if arguments[0] == "login":
        assert sys.stdin.read().strip() == "test-only-placeholder"
    if arguments[0] == "build" and os.environ.get("MOCK_FAIL_BUILD") == "true":
        raise SystemExit(42)
    if arguments[0] == "push" and os.environ.get("MOCK_FAIL_PUSH") == "true":
        raise SystemExit(43)
elif tool == "helm":
    assert sys.stdin.read().strip() == "{}"
'''
        for tool in ("aws", "terraform", "docker", "helm", "kubectl", "python3"):
            executable = self.bin / tool
            executable.write_text(mock)
            executable.chmod(0o755)

    def deploy(self, **settings):
        environment = dict(os.environ)
        environment.update({
            "PATH": str(self.bin) + os.pathsep + environment.get("PATH", ""),
            "MOCK_LOG": str(self.log), "MOCK_STATE": str(self.state),
            "MAKEFLAGS": "", "MFLAGS": "",
        })
        environment.update(settings)
        result = subprocess.run(
            [shutil.which("make"), "--no-print-directory", "eks-deploy"],
            cwd=self.root, env=environment, capture_output=True, text=True,
        )
        commands = [json.loads(line) for line in self.log.read_text().splitlines()]
        return result, commands

    def test_from_scratch_build_push_and_rollout(self):
        result, commands = self.deploy()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        apply = next(index for index, (tool, args) in enumerate(commands) if tool == "terraform" and "apply" in args)
        build = next(index for index, (tool, args) in enumerate(commands) if tool == "docker" and args[0] == "build")
        push = next(index for index, (tool, args) in enumerate(commands) if tool == "docker" and args[0] == "push")
        helm = next(index for index, (tool, args) in enumerate(commands) if tool == "helm")
        rollout = next(index for index, (tool, args) in enumerate(commands) if tool == "kubectl" and "restart" in args)
        self.assertLess(apply, build)
        self.assertLess(build, push)
        self.assertLess(push, helm)
        self.assertLess(helm, rollout)
        self.assertIn("linux/amd64", commands[build][1])
        self.assertIn("123456789012.dkr.ecr.us-east-1.amazonaws.com/nebraska-eks-app:test-tag", commands[push][1])
        self.assertIn("http://example.test", result.stdout)

    def test_custom_repository_skips_publishing(self):
        result, commands = self.deploy(MOCK_BUILD_LOCAL="false")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse(any(tool == "docker" and args[0] in ("build", "push", "login") for tool, args in commands))
        self.assertTrue(any(tool == "helm" for tool, args in commands))

    def test_build_failure_prevents_push_and_install(self):
        result, commands = self.deploy(MOCK_FAIL_BUILD="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(tool == "docker" and args[0] == "push" for tool, args in commands))
        self.assertFalse(any(tool == "helm" for tool, args in commands))

    def test_push_failure_prevents_install(self):
        result, commands = self.deploy(MOCK_FAIL_PUSH="true")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(tool == "helm" for tool, args in commands))


if __name__ == "__main__":
    unittest.main()