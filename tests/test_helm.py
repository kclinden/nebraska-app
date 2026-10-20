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

    def test_application_metadata_is_consistent(self):
        documents = self.render()
        for item in documents:
            with self.subTest(kind=item["kind"], name=item["metadata"]["name"]):
                self.assertEqual(item["metadata"]["labels"]["Application"], "Husker-Roster-App")
                self.assertEqual(item["metadata"]["labels"]["app.kubernetes.io/part-of"], "husker-roster-app")
                self.assertEqual(item["metadata"]["annotations"]["Application"], "Husker-Roster-App")
                self.assertEqual(item["metadata"]["annotations"]["app.kubernetes.io/part-of"], "husker-roster-app")

                pod_template = None
                if item["kind"] in ("Deployment", "Job"):
                    pod_template = item["spec"]["template"]
                elif item["kind"] == "CronJob":
                    pod_template = item["spec"]["jobTemplate"]["spec"]["template"]
                if pod_template:
                    self.assertEqual(pod_template["metadata"]["labels"]["Application"], "Husker-Roster-App")
                    self.assertEqual(pod_template["metadata"]["annotations"]["Application"], "Husker-Roster-App")

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
        self.assertFalse(any(item["metadata"]["name"].endswith(("-seed", "-dynamodb")) for item in documents))
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

    def test_sports_source_configuration(self):
        for values, source in (([], "synced"), (["--set", "sportsData.source=storage"], "storage")):
            with self.subTest(source=source):
                documents = self.render(*values)
                deployment = next(item for item in documents if item["kind"] == "Deployment" and item["metadata"]["name"] == "nebraska-app")
                environment = {entry["name"]: entry["value"] for entry in deployment["spec"]["template"]["spec"]["containers"][0]["env"]}
                self.assertEqual(environment["SPORTS_DATA_SOURCE"], source)
                self.assertNotIn("ESPN_CACHE_SECONDS", environment)
                self.assertEqual(environment["ESPN_SEASON"], "2026")

    def test_scheduled_and_initial_sync_share_pod_identity(self):
        documents = self.render("--set", "seed.enabled=false,dynamodb.enabled=false,dynamodb.useStaticCredentials=false,serviceAccount.create=true")
        cron = next(item for item in documents if item["kind"] == "CronJob")
        self.assertEqual(cron["spec"]["schedule"], "*/15 * * * *")
        self.assertEqual(cron["spec"]["concurrencyPolicy"], "Forbid")
        initial = next(item for item in documents if item["kind"] == "Job")
        self.assertEqual(initial["metadata"]["annotations"]["helm.sh/hook-weight"], "10")
        for pod in (cron["spec"]["jobTemplate"]["spec"]["template"]["spec"], initial["spec"]["template"]["spec"]):
            self.assertEqual(pod["serviceAccountName"], "nebraska-app")
            container = pod["containers"][0]
            self.assertEqual(container["command"], ["python", "-m", "espn"])
            self.assertEqual(container["envFrom"], [{"secretRef": {"name": "nebraska-app-aws"}}])

    def test_legacy_mode_or_disabled_sync_has_no_sync_jobs(self):
        for settings in ("sportsData.source=storage", "sportsData.sync.enabled=false"):
            with self.subTest(settings=settings):
                documents = self.render("--set", settings)
                self.assertFalse(any("espn-sync" in item["metadata"]["name"] or "espn-initial-sync" in item["metadata"]["name"] for item in documents))


if __name__ == "__main__":
    unittest.main()