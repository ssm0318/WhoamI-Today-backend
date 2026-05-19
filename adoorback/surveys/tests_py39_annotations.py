import ast
from pathlib import Path

from django.test import SimpleTestCase


BACKEND_ROOT = Path(__file__).resolve().parents[1]


class Python39AnnotationCompatibilityTests(SimpleTestCase):
    def test_modules_using_pep604_function_annotations_postpone_evaluation(self):
        offenders = []

        for path in sorted(BACKEND_ROOT.rglob('*.py')):
            source = path.read_text()
            tree = ast.parse(source, filename=str(path))
            has_future_annotations = any(
                isinstance(node, ast.ImportFrom)
                and node.module == '__future__'
                and any(alias.name == 'annotations' for alias in node.names)
                for node in tree.body
            )
            if has_future_annotations:
                continue

            for node in ast.walk(tree):
                if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                annotations = [node.returns]
                annotations.extend(arg.annotation for arg in node.args.args)
                annotations.extend(arg.annotation for arg in node.args.kwonlyargs)
                if node.args.vararg:
                    annotations.append(node.args.vararg.annotation)
                if node.args.kwarg:
                    annotations.append(node.args.kwarg.annotation)
                if any(self._uses_pep604_union(annotation) for annotation in annotations):
                    offenders.append(f'{path.relative_to(BACKEND_ROOT)}:{node.lineno}')

        self.assertEqual([], offenders)

    @staticmethod
    def _uses_pep604_union(annotation):
        if annotation is None or isinstance(annotation, ast.Constant):
            return False
        return any(
            isinstance(node, ast.BinOp) and isinstance(node.op, ast.BitOr)
            for node in ast.walk(annotation)
        )
