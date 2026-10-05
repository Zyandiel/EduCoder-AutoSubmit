import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from educoder.solution_files import load_files, write_solution


class SolutionFilesTests(unittest.TestCase):
    def test_missing_header_prevents_any_browser_edit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / '2.cpp'
            source.write_text('int Fact(int n){return n;}', encoding='utf-8')
            source.with_suffix('.files.json').write_text(
                json.dumps({'step2/fact.cpp': '2.cpp', 'step2/fact.h': 'missing.h'}), encoding='utf-8')
            page = MagicMock()
            with self.assertRaises(ValueError):
                write_solution(page, source, root)
            self.assertEqual(page.mock_calls, [])

    def test_mapping_cannot_escape_assignment_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / 'assignment' / '1.cpp'
            source.parent.mkdir()
            source.write_text('int x;', encoding='utf-8')
            (root / 'outside.cpp').write_text('private', encoding='utf-8')
            source.with_suffix('.files.json').write_text(
                json.dumps({'step/source.cpp': '../outside.cpp'}), encoding='utf-8')
            with self.assertRaises(ValueError):
                load_files(source)

    def test_example_mapping_contains_source_and_header(self):
        root = Path(__file__).resolve().parents[1]
        source = root / 'examples' / 'solutions' / '示例实训' / '2.cpp'
        files = load_files(source)
        self.assertEqual([remote for remote, _ in files], ['step2/main.cpp', 'step2/greeting.h'])
        self.assertTrue(all(path.is_file() for _, path in files))
