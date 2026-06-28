import unittest
from unittest.mock import patch
from pathlib import Path
from local_coder.task_annotator import TaskAnnotator, CodeSearchResult, AnnotationResult

class TestTaskAnnotator(unittest.TestCase):
    @patch('local_coder.task_annotator.TaskAnnotator._query_codesearch')
    def test_file_creation_annotation_no_lines(self, mock_query):
        annotator = TaskAnnotator(project_root=Path('/tmp/dummy'))
        mock_query.return_value = CodeSearchResult(file_path='src/new_module.py', start_line=None, end_line=None, found=True)
        
        result = annotator.annotate_task('Create a new module', ['new_module'])
        
        self.assertEqual(result.annotations, ['<!-- target: src/new_module.py -->'])

    @patch('local_coder.task_annotator.TaskAnnotator._query_codesearch')
    def test_warning_for_unresolved_path(self, mock_query):
        annotator = TaskAnnotator(project_root=Path('/tmp/dummy'))
        mock_query.return_value = CodeSearchResult(file_path='unknown.py', start_line=None, end_line=None, found=False)
        
        result = annotator.annotate_task('Create a new module', ['unknown'])
        
        self.assertIn("CodeSearch returned no results for 'unknown'", result.warnings)

    @patch('local_coder.task_annotator.TaskAnnotator._query_codesearch')
    def test_multi_file_respects_50_cap(self, mock_query):
        annotator = TaskAnnotator(project_root=Path('/tmp/dummy'))
        mock_query.return_value = CodeSearchResult(file_path='dummy.py', start_line=None, end_line=None, found=True)
        
        result = annotator.annotate_task('Create multiple modules', ['module1', 'module2'] * 30)
        
        self.assertEqual(len(result.annotations), 50)

    @patch('local_coder.task_annotator.TaskAnnotator._query_codesearch')
    def test_annotation_with_lines(self, mock_query):
        annotator = TaskAnnotator(project_root=Path('/tmp/dummy'))
        mock_query.return_value = CodeSearchResult(file_path='src/handler.py', start_line=10, end_line=42, found=True)
        
        result = annotator.annotate_task('Update handler', ['handler'])
        
        self.assertEqual(result.annotations, ['<!-- target: src/handler.py lines: 10-42 -->'])

if __name__ == '__main__':
    unittest.main()