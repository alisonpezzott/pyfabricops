import ast
import os
import subprocess
from pathlib import Path


def get_public_functions_and_classes(file_path):
    """Extracts functions and publics class from a python file."""
    public_items = []

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()

        tree = ast.parse(content)
        
        # Check if __all__ is defined in the module
        has_all = False
        all_items_from_module = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id == '__all__':
                        has_all = True
                        # Extract items from __all__ list
                        if isinstance(node.value, ast.List):
                            for elt in node.value.elts:
                                if isinstance(elt, ast.Str):  # Python < 3.8
                                    all_items_from_module.append(elt.s)
                                elif isinstance(elt, ast.Constant) and isinstance(elt.value, str):  # Python >= 3.8
                                    all_items_from_module.append(elt.value)
        
        # If __all__ is defined, use only those items
        if has_all:
            return all_items_from_module
        
        # Otherwise, use the original logic (all public functions/classes)
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if not node.name.startswith('_'):
                    public_items.append(node.name)
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith('_'):
                    public_items.append(node.name)
                    
    except Exception as e:
        print(f'Error processing {file_path}: {e}')

    return public_items


def generate_init_file(src_dir):
    """Generate the content __init__.py automatically."""
    src_path = Path(src_dir)

    imports = []
    all_items = []

    # Iterate over .py files on root path
    for py_file in src_path.glob('*.py'):
        if py_file.name in ['__init__.py', '_version.py']:
            continue

        module_name = py_file.stem
        public_items = get_public_functions_and_classes(py_file)

        if public_items:
            import_module = module_name
            imports.append(
                f"from .{import_module} import {', '.join(public_items)}"
            )
            all_items.extend(public_items)

    # Iterate subfolders
    for subdir in src_path.iterdir():
        if (
            subdir.is_dir()
            and not subdir.name.startswith('_')
            and subdir.name != '__pycache__'
        ):
            for py_file in subdir.glob('*.py'):
                if py_file.name in ['__init__.py']:
                    continue

                module_name = py_file.stem
                public_items = get_public_functions_and_classes(py_file)

                if public_items:
                    # For subfolders use full path
                    import_module = f'{subdir.name}.{module_name}'
                    imports.append(
                        f"from .{import_module} import {', '.join(public_items)}"
                    )
                    all_items.extend(public_items)

    # Special imports
    special_imports = [
        'from ._version import __version__',
    ]

    # Generate the __init__.py content
    content = []

    # Add special imports
    content.extend(special_imports)
    content.append('')

    # Add the imports
    content.extend(sorted(imports))
    content.append('')

    # Add __all__
    all_items_sorted = sorted(set(all_items))

    content.append('__all__ = [')
    for item in sorted(set(all_items_sorted)):
        content.append(f"    '{item}',")
    content.append(']')

    return '\n'.join(content)


def run_formatter(tool: str, file_path: str):
    """Run a code formatter on the specified file."""
    print(f'🔄 Running {tool} on {file_path}...')
    try:
        result = subprocess.run(
            [tool, file_path],
            check=True,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
        )  # Ignora caracteres problemáticos
        print(f'✅ {tool} completed successfully!')
        if result.stdout:
            print(f'Output: {result.stdout}')
        return True
    except subprocess.CalledProcessError as e:
        print(f'❌ {tool} failed: {e}')
        if e.stderr:
            print(f'Error output: {e.stderr}')
        return False
    except FileNotFoundError:
        print(
            f'❌ {tool} not found. Make sure {tool} is installed and in PATH.'
        )
        return False
    except UnicodeDecodeError as e:
        print(f'❌ {tool} encoding error: {e}')
        # Tenta executar sem capturar a saída
        try:
            subprocess.run([tool, file_path], check=True)
            print(f'✅ {tool} completed successfully (without output capture)!')
            return True
        except subprocess.CalledProcessError:
            return False


if __name__ == '__main__':
    src_dir = 'src/pyfabricops'
    content = generate_init_file(src_dir)

    # write __init__.py
    init_file = os.path.join(src_dir, '__init__.py')
    with open(init_file, 'w', encoding='utf-8') as f:
        f.write(content)

    print(f'✅ {init_file} generated automatically!')
    total_items = content.split('__all__')[1].count(',')
    print(f'📦 {total_items} exported items.')

    # run blue and isort on __init__.py
    run_formatter('blue', init_file)
    run_formatter('isort', init_file)
