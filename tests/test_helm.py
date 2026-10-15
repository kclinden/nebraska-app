from pathlib import Path
import importlib.util
import shutil
import subprocess
import unittest


@unittest.skipUnless(shutil.which("helm") and importlib.util.find_spec("yaml"), "Helm and PyYAML are required for chart tests")
class HelmTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import yaml

        cls.yaml = yaml
        cls.root = Path(__file__).resolve().parents[1]

    def render(self, *values):
        command = ["helm", "template", "nebraska-app", "charts/nebraska-app"]
        for key, value in (
            ("seed.script", "scripts/seed_local_dynamodb.py"),
            ("seed.roster", "data/roster.yaml"),
            ("seed.schedule", "data/schedule.yaml"),
        ):
            command.extend(["--set-file", f"{key}={value}"])
        command.extend(values)
        result = subprocess.run(command, cwd=self.root, capture_output=True, text=True, check=True)
        return [document for document in self.yaml.safe_load_all(result.stdout) if document]

    def test_local_defaults(self):
        documents = self.render()
        secret = next(item for item in documents if item["kind"] == "Secret" and item["metadata"]["name"].endswith("-aws"))
        self.assertEqual(secret["stringData"]["AWS_ACCESS_KEY_ID"], "local")
        self.assertEqual(secret["stringData"]["AWS_ENDPOINT_URL_DYNAMODB"], "http://nebraska-app-dynamodb:8000")
        self.assertEqual(secret["stringData"]["DYNAMODB_PLAYERS_TABLE"], "NebraskaPlayers")
        self.assertTrue(any(item["kind"] == "Job" for item in documents))
        self.assertFalse(any(item["kind"] == "ServiceAccount" for item in documents))

    def test_eks_identity(self):
        documents = self.render(
            "--set", "seed.enabled=false,dynamodb.enabled=false,dynamodb.useStaticCredentials=false",
            "--set", "serviceAccount.create=true,serviceAccount.name=nebraska-app",
            "--set", "dynamodb.tables.players=nebraska-eks-players,dynamodb.tables.schedule=nebraska-eks-schedule,dynamodb.tables.users=nebraska-eks-users",
        )
        secret = next(item for item in documents if item["kind"] == "Secret" and item["metadata"]["name"].endswith("-aws"))
        for key in ("AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "AWS_ENDPOINT_URL_DYNAMODB"):
            self.assertNotIn(key, secret["stringData"])
        self.assertEqual(secret["stringData"]["DYNAMODB_USERS_TABLE"], "nebraska-eks-users")
        deployment = next(item for item in documents if item["kind"] == "Deployment")
        self.assertEqual(deployment["spec"]["template"]["spec"]["serviceAccountName"], "nebraska-app")
        self.assertTrue(any(item["kind"] == "ServiceAccount" for item in documents))
        self.assertFalse(any(item["kind"] == "Job" or item["metadata"]["name"].endswith("-dynamodb") for item in documents))
        service = next(item for item in documents if item["kind"] == "Service")
        self.assertEqual(service["spec"]["type"], "ClusterIP")

    def test_public_alb_service(self):
        documents = self.render("--set", "service.type=NodePort,service.nodePort=32080")
        service = next(item for item in documents if item["kind"] == "Service" and item["metadata"]["name"] == "nebraska-app")
        self.assertEqual(service["spec"]["type"], "NodePort")
        self.assertEqual(service["spec"]["ports"][0]["nodePort"], 32080)
        self.assertFalse(any(item["kind"] == "Ingress" for item in documents))

    def test_public_eks_notes(self):
        result = subprocess.run([
            "helm", "install", "nebraska-preview", "charts/nebraska-app",
            "--dry-run=client", "--hide-secret", "--set",
            "seed.enabled=false,dynamodb.enabled=false,dynamodb.useStaticCredentials=false,service.type=NodePort",
        ], cwd=self.root, capture_output=True, text=True, check=True)
        self.assertIn("make eks-url", result.stdout)


if __name__ == "__main__":
    unittest.main()