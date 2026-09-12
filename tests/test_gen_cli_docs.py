"""Regression checks for parser/documentation drift and cross-platform extraction."""

import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('gen_cli_docs', ROOT / 'scripts/gen_cli_docs.py')
GEN = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(GEN)


class CliDocsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ('src', 'doc'):
            (self.root / directory).mkdir()
        for name in ('utils.c', 'local.c', 'server.c', 'tunnel.c', 'redir.c',
                     'manager.c', 'ss-nat', 'aead.c', 'stream.c'):
            shutil.copyfile(ROOT / 'src' / name, self.root / 'src' / name)
        for path in (ROOT / 'doc').glob('*.asciidoc'):
            shutil.copyfile(path, self.root / 'doc' / path.name)

    def change(self, filename, old, new):
        path = self.root / filename
        source = path.read_text()
        self.assertIn(old, source)
        path.write_text(source.replace(old, new))

    def test_checked_in_pages_and_idempotence(self):
        generated = GEN.generate(self.root)
        self.assertEqual(len(generated), 7)
        for name, text in generated.items():
            self.assertEqual(text, (self.root / 'doc' / name).read_text())
            (self.root / 'doc' / name).write_text(text)
        self.assertEqual(generated, GEN.generate(self.root))

    def test_platform_options_aliases_and_program_specific_flags(self):
        pages = GEN.generate(self.root)
        self.assertIn('-S <path>::\nAndroid only', pages['ss-local.asciidoc'])
        self.assertIn('-V::\nAndroid only', pages['ss-tunnel.asciidoc'])
        self.assertIn('--nftables-sets <sets>::\nLinux builds', pages['ss-server.asciidoc'])
        self.assertIn('-I <interface>::', pages['ss-nat.asciidoc'])
        self.assertIn('--password <password>::', pages['ss-tunnel.asciidoc'])
        self.assertIn('--workdir <path>::', pages['ss-manager.asciidoc'])
        self.assertNotIn('[-p ', pages['ss-manager.asciidoc'])
        self.assertNotIn('--tcp-incoming-sndbuf', pages['ss-manager.asciidoc'])
        self.assertIn('-A::\nDeprecated', pages['ss-manager.asciidoc'])

    def test_new_option_requires_description(self):
        self.change('src/local.c', '"reuse-port",', '"new-option",')
        with self.assertRaisesRegex(ValueError, 'missing CLI_DOC.*new-option'):
            GEN.generate(self.root)

    def test_argument_arity_is_checked(self):
        self.change('src/local.c', '"reuse-port",  no_argument',
                    '"reuse-port",  required_argument')
        with self.assertRaisesRegex(ValueError, 'argument mismatch.*reuse-port'):
            GEN.generate(self.root)

    def test_unknown_table_syntax_fails_closed(self):
        self.change('src/local.c', '"reuse-port",  no_argument',
                    '"reuse-port",  optional_argument')
        with self.assertRaisesRegex(ValueError, 'Unsupported long_options'):
            GEN.generate(self.root)

    def test_nonliteral_short_options_fail_closed(self):
        self.change('src/local.c', '"f:s:p:l:k:t:m:i:c:b:a:n:huUv6A"', 'SHORT_OPTIONS')
        with self.assertRaisesRegex(ValueError, 'literal getopt_long'):
            GEN.generate(self.root)

    def test_shell_arity_and_new_flags(self):
        self.change('src/ss-nat', ':s:l:S:L:i:I:e:a:b:w:ouUfh', ':s:l:S:L:i:I:e:a:b:w:ouUfhz')
        with self.assertRaisesRegex(ValueError, 'missing CLI_DOC.*-z'):
            GEN.generate(self.root)

    def test_stale_override_is_rejected(self):
        self.change('src/server.c', '-p <server_port>::', '--unused <server_port>::')
        with self.assertRaisesRegex(ValueError, 'stale CLI_DOC'):
            GEN.generate(self.root)

    def test_cipher_table_changes_propagate(self):
        self.change('src/aead.c', '"aes-128-gcm",', '"new-aead-cipher",')
        self.assertIn('new-aead-cipher', GEN.generate(self.root)['ss-local.asciidoc'])

    def test_check_detects_stale_docs_and_build_output_preserves_source(self):
        self.change('doc/ss-local.asciidoc', '--mtu <MTU>::', '--mtu <WRONG>::')
        command = [sys.executable, str(ROOT / 'scripts/gen_cli_docs.py'),
                   '--root', str(self.root)]
        checked = subprocess.run(command + ['--check'], capture_output=True, text=True)
        self.assertNotEqual(checked.returncode, 0)
        self.assertIn('Stale CLI docs', checked.stderr)
        output = self.root / 'generated'
        subprocess.run(command + ['--output-dir', str(output)], check=True)
        self.assertIn('--mtu <MTU>::', (output / 'ss-local.asciidoc').read_text())
        self.assertIn('--mtu <WRONG>::', (self.root / 'doc/ss-local.asciidoc').read_text())


if __name__ == '__main__':
    unittest.main()
