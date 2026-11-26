"""Upgrading data created by earlier versions."""

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase

BEFORE = [("accounts", "0004_cache_table")]
AFTER = [("accounts", "0005_email_ci_unique")]


class EmailUniquenessUpgradeTests(TransactionTestCase):
    def migrate(self, targets):
        executor = MigrationExecutor(connection)
        executor.migrate(targets)
        return MigrationExecutor(connection).loader.project_state(targets).apps

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())

    def test_names_the_accounts_to_fix_without_printing_addresses(self):
        users = self.migrate(BEFORE).get_model("accounts", "User")
        first = users.objects.create(username="a", email="same@example.test")
        second = users.objects.create(username="b", email="SAME@example.test")
        with self.assertRaisesMessage(RuntimeError, f"User IDs: [{first.pk}, {second.pk}]"):
            self.migrate(AFTER)
        users.objects.filter(pk=second.pk).delete()
        self.migrate(AFTER)
