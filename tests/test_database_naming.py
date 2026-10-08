import unittest
from unittest.mock import MagicMock, patch

import db_router


class DatabaseNamingTests(unittest.TestCase):
    def test_company_database_names(self):
        for company, expected in [('DEMO001', 'qiy_demo001'), ('COMP002', 'qiy_comp002'), (1, 'qiy_1')]:
            with self.subTest(company=company):
                self.assertEqual(db_router._db_name(company), expected)
                self.assertEqual(db_router._build_uri(company).database, expected)

    def test_new_company_provisioning_uses_qiy_database(self):
        engine = MagicMock()
        with patch.object(db_router, 'create_engine', return_value=engine) as create:
            db_router._create_database_if_missing('COMP002')
        self.assertIsNone(create.call_args.args[0].database)
        connection = engine.connect.return_value.__enter__.return_value
        sql = str(connection.execute.call_args.args[0])
        self.assertIn('CREATE DATABASE IF NOT EXISTS `qiy_comp002`', sql)
        connection.commit.assert_called_once()
        engine.dispose.assert_called_once()

    def test_platform_default_stays_qiyadah_erp(self):
        with patch.dict('os.environ', {}, clear=True), patch('sqlalchemy.create_engine') as create:
            db_router.get_platform_engine()
        self.assertEqual(create.call_args.args[0], 'mysql+pymysql://root@localhost/qiyadah_erp')


if __name__ == '__main__':
    unittest.main()
