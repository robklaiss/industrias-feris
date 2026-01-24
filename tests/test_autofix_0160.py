#!/usr/bin/env python3
"""Test anti-regresión para verify que --bump-doc se pasa correctamente con argumento"""

import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path
import sys

# Agregar el directorio de tools al path
sys.path.insert(0, str(Path(__file__).parent.parent / "tesaka-cv" / "tools"))

from autofix_0160_gTotSub import run_send_sirecepde


class TestAutofixBumpDoc(unittest.TestCase):
    """Test que verify que el comando send_sirecepde.py recibe --bump-doc con valor correcto"""

    @patch('autofix_0160_gTotSub.run_command')
    @patch('autofix_0160_gTotSub.find_latest_file')
    def test_send_xml_command_construction(self, mock_find_latest, mock_run_command):
        """Test que el comando construido incluye --bump-doc con valor cuando bump_doc=1"""
        # Setup
        mock_run_command.return_value = MagicMock(returncode=0)
        mock_find_latest.return_value = Path("response_recepcion_test_iter1.json")
        
        artifacts_dir = Path("/tmp/artifacts")
        xml_path = Path("test.xml")
        
        # Test case 1: bump_doc=True debe incluir --bump-doc 1
        with patch('sys.exit'):  # Prevenir sys.exit en caso de error
            run_send_sirecepde(
                env='test',
                xml_path=xml_path,
                artifacts_dir=artifacts_dir,
                iteration=1,
                bump_doc=True,
                dump_http=False
            )
        
        # Verificar que run_command fue llamado con el comando correcto
        called_cmd = mock_run_command.call_args[0][0]
        self.assertIn('--bump-doc', called_cmd)
        bump_index = called_cmd.index('--bump-doc')
        self.assertEqual(called_cmd[bump_index + 1], '1')
        
        # Reset mock para siguiente test
        mock_run_command.reset_mock()
        
        # Test case 2: bump_doc=False NO debe incluir --bump-doc
        with patch('sys.exit'):  # Prevenir sys.exit en caso de error
            run_send_sirecepde(
                env='test',
                xml_path=xml_path,
                artifacts_dir=artifacts_dir,
                iteration=1,
                bump_doc=False,
                dump_http=False
            )
        
        # Verificar que run_command fue llamado sin --bump-doc
        called_cmd = mock_run_command.call_args[0][0]
        self.assertNotIn('--bump-doc', called_cmd)
        
        # Reset mock para siguiente test
        mock_run_command.reset_mock()
        
        # Test case 3: con dump_http=True también debe funcionar
        with patch('sys.exit'):  # Prevenir sys.exit en caso de error
            run_send_sirecepde(
                env='test',
                xml_path=xml_path,
                artifacts_dir=artifacts_dir,
                iteration=1,
                bump_doc=True,
                dump_http=True
            )
        
        # Verificar que run_command fue llamado con todo correcto
        called_cmd = mock_run_command.call_args[0][0]
        self.assertIn('--bump-doc', called_cmd)
        self.assertIn('--dump-http', called_cmd)
        bump_index = called_cmd.index('--bump-doc')
        self.assertEqual(called_cmd[bump_index + 1], '1')


if __name__ == '__main__':
    unittest.main()
