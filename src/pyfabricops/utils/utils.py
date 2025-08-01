import base64
import fnmatch
import glob
import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import json5
import pandas
from pandas import DataFrame

from .exceptions import (
    ConfigurationError,
    FileNotFoundError,
    ResourceNotFoundError,
)
from .logging import get_logger

logger = get_logger(__name__)


def copy_to_staging(path: str) -> str:
    """
    Copies the contents of the specified directory to a staging folder.
    This function ensures that a staging folder exists, and if it already exists,
    it removes the existing staging folder and creates a new one. It then copies
    all files and directories from the specified path to the staging folder.

    Args:
        path (str): The path of the directory to be copied to the staging folder.

    Returns:
        str: The path to the staging folder where the contents have been copied.

    Examples:
        ```python
        copy_to_staging('/path/to/directory')
        ```
    """
    current_folder = os.path.dirname(__file__)

    # ensure staging folder exists
    path_staging = os.path.join(current_folder, '_stg', os.path.basename(path))

    if os.path.exists(path_staging):
        shutil.rmtree(path_staging)

    os.makedirs(path_staging)

    # copy files to staging folder
    shutil.copytree(path, path_staging, dirs_exist_ok=True)

    return path_staging


def read_json(path: str) -> dict:
    """
    Reads a JSON file from the specified path and returns its contents as a dictionary.


    Args:
        path (str): The file path to the JSON file.


    Returns:
        dict: The contents of the JSON file.


    Raises:
        ResourceNotFoundError: If the file does not exist at the specified path.

    Examples:
        ```python
        read_json('data.json')
        ```
    """
    try:
        with open(path, 'r', encoding='utf-8') as file:
            data = json.load(file)
    except FileNotFoundError as e:
        logger.error(f'Error reading JSON file: {e}')
        return {}
    return data


def write_json(data: dict, path: str) -> None:
    """
    Writes the given data to a JSON file at the specified path.

    Args:
        data (dict): The data to be written to the JSON file.
        path (str): The file path where the JSON should be saved.

    Returns:
        None

    Examples:
        ```python
        write_json({'key': 'value'}, 'output.json')
        ```
    """
    if not os.path.exists(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, indent=4)


def get_root_path() -> Path:
    """
    Find the root path.
    """
    return os.getcwd()


def get_current_branch(branch: str = None) -> str:
    """
    Get the name of the current local branch

    Args:
        branch(str, optional): Branch to bypass the auto get current branch.

    Returns:
        str: The branch name

    Raises:
        ConfigurationError: Fallbak to main if error

    Examples:
        ```python
        get_current_branch()
        ```
    """
    if not branch is None:
        return branch
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--abbrev-ref', 'HEAD'],
            capture_output=True,
            text=True,
            check=True,
        )
        branch = result.stdout.strip()
        return branch
    except ConfigurationError:
        logger.error(
            'Error getting the branch name. Are you in a git repository?'
        )
        return 'main'  # default fallback


def get_workspace_suffix(branch: str, branches_path: str) -> str:
    """
    Returns the workspace suffix configured in branches.json

    Args:
        branch(str): Branch of the repository.
        branches_path(str): The path of branches.json.

    Returns:
        str: The workspace name suffix

    Examples:
        ```python
        get_workspace_suffix('main')
        ```
    """
    try:
        branches_dict = read_json(branches_path)
    except:
        raise ResourceNotFoundError(f'Dict not found at {branches_path}')

    try:
        suffix = branches_dict[branch]
    except KeyError:
        raise ResourceNotFoundError(
            'The branch is not configured in branches dictionary.'
        )

    return suffix


def is_valid_uuid(input: str) -> bool:
    """
    Check if the input string is a valid UUID.

    Args:
        input (str): The string to check.

    Returns:
        bool: True if the input is a valid UUID, False otherwise.

    Examples:
        ```python
        is_valid_uuid('123e4567-e89b-12d3-a456-426614174000')
        ```
    """
    try:
        uuid.UUID(input)
        return True
    except ValueError:
        return False


def pack_item_definition(
    path: str,
    exclude_paths: list = None,
    exclude_patterns: list = ['*/.pbi/localSettings.json', '*/.pbi/cache.abf'],
) -> dict[dict, str]:
    """
    Pack the definition files into a JSON structure.

    Args:
        path (str): The path to the project directory.
        exclude_paths (list): List of exact paths to exclude from packing.
        exclude_patterns (list): List of glob patterns to exclude from packing. e.g.  ['*/.pbi/localSettings.json', '*/.pbi/cache.abf']

    Returns:
        dict: A dictionary containing the packed definition.

    Raises:
        ConfigurationError: If the path does not exist or is not a directory.

    Examples:
        ```python
        pack_item_definition('MainProject/workspace/path/to/Financials.SemanticModel')
        ```
    """
    parts = []
    exclude_paths = exclude_paths or []
    exclude_patterns = exclude_patterns or []

    # Walk through path recursively
    for dirpath, dirnames, filenames in os.walk(path):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            # Compute path relative to input_path
            rel_path = os.path.relpath(full_path, path).replace(os.sep, '/')

            # Skip exact matches
            if rel_path in exclude_paths:
                print(f'Skipping (exact): {rel_path}')
                continue
            # Skip patterns
            if any(fnmatch.fnmatch(rel_path, pat) for pat in exclude_patterns):
                print(f'Skipping (pattern): {rel_path}')
                continue

            # Read and encode file
            with open(full_path, 'rb') as f:
                payload_b64 = base64.b64encode(f.read()).decode('utf-8')

            parts.append(
                {
                    'path': rel_path,
                    'payload': payload_b64,
                    'payloadType': 'InlineBase64',
                }
            )

    # Build model object
    model = {'parts': parts}

    return model


def unpack_item_definition(item_definition: dict, path: str) -> None:
    """
    Unpack files from JSON definition to a directory structure.

    Args:
        definition (dict): The JSON definition containing the files to unpack.
        path (str): The root path where the files will be unpacked.

    Returns:
        None

    Examples:
        ```python
        unpack_item_definition(item_definition, '/path/to/output/directory')
        ```
    """
    # Iterate over each part of the model
    for part in item_definition.get('definition', {}).get('parts', []):
        relative_path = part[
            'path'
        ]   # Relative file path (e.g., "definition/tables/..." or ".platform")
        payload_b64 = part['payload']  # Base64 content

        # Decode the payload
        content_bytes = base64.b64decode(payload_b64)

        # Build the full output path
        out_path = os.path.join(path, relative_path)
        parent_dir = os.path.dirname(out_path)

        # Create directories as needed (ignore files in the root)
        if parent_dir and not os.path.exists(parent_dir):
            os.makedirs(parent_dir, exist_ok=True)

        # Write the decoded file
        with open(out_path, 'wb') as out_file:
            out_file.write(content_bytes)

    logger.success(f'Item definition unpacked to {path}')


def parse_tmdl_parameters(path: str) -> dict:
    """
    Parse TMDL parameters from a file.

    Args:
        path (str): The path to the TMDL file.

    Returns:
        dict: A dictionary containing the parsed parameters.

    Raises:
        FileNotFoundError: If the specified file does not exist.
        ValueError: If the file content is not in the expected format.

    Examples:
        ```python
        parse_tmdl_parameters('MyProject/workspace/path/to/Financials.SemanticModel/definition/expressions.tmdl')
        ```
    """
    # Check if the file exists
    if not os.path.exists(path):
        raise FileNotFoundError(f'File not found: {path}')

    try:
        with open(path, 'r', encoding='utf-8') as f:
            expressions = f.read()
    except Exception as e:
        raise ValueError(f'Error reading file {path}: {str(e)}')

    params = {}

    # Pattern 1: Import model - expression VariableName = "Value"
    pattern1 = r'expression\s+(\w+)\s*=\s*"([^"]*)"'
    matches1 = re.findall(pattern1, expressions)

    for match in matches1:
        variable_name = match[0]
        variable_value = match[1]
        # Skip if it's already a placeholder
        if not (
            variable_value.startswith('#{') and variable_value.endswith('}#')
        ):
            params[variable_name] = variable_value

    # Pattern 2: Parameters starting with # (like #date, #datetime, #time, etc.)
    pattern2 = r'expression\s+(\w+)\s*=\s*(#\w+\([^)]*\))'
    matches2 = re.findall(pattern2, expressions)

    for match in matches2:
        variable_name = match[0]
        variable_value = match[1]
        # Skip if it's already a placeholder
        if not (
            variable_value.startswith('#{') and variable_value.endswith('}#')
        ):
            params[variable_name] = variable_value

    # Pattern 3: Direct Lake - Sql.Database("server", "database")
    pattern3 = r'Sql\.Database\s*\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)'
    matches3 = re.findall(pattern3, expressions)

    for match in matches3:
        server_value = match[0]
        database_value = match[1]

        # Skip if they're already placeholders
        if not (server_value.startswith('#{') and server_value.endswith('}#')):
            params['ServerEndpoint'] = server_value
        if not (
            database_value.startswith('#{') and database_value.endswith('}#')
        ):
            params['DatabaseId'] = database_value

    if not params:
        logger.warning(f'No parameters found in file: {path}')

    return params


def parse_definition_report(path: str) -> dict:
    """
    Parse a Power BI report definition file to extract workspace and semantic model information.

    Args:
        path (str): The path to the Power BI report definition file.

    Returns:
        dict: A dictionary containing the workspace name, semantic model name, and semantic model ID.

    Raises:
        ResourceNotFoundError: If the specified file does not exist or is not in the expected format.
        FileNotFoundError: If the specified file does not exist.
        json.JSONDecodeError: If the file content is not valid JSON.

    Examples:
        ```python
        parse_definition_report('MyProject/workspace/path/to/Financials.Report/definition.pbir')
        ```
    """
    with open(path, encoding='utf-8') as f:
        data = json.load(f)

    # Check if the file contains the expected structure
    if (
        'datasetReference' not in data
        or 'byConnection' not in data['datasetReference']
    ):
        raise ResourceNotFoundError(
            f'Invalid report definition file: {path}. Expected structure not found.'
        )
    by_conn = data['datasetReference']['byConnection']
    conn_str = by_conn['connectionString']
    model_id = by_conn['pbiModelDatabaseName']

    # 1) workspace_name: part after the last slash and before the semicolon
    workspace_name = conn_str.split('/')[-1].split(';')[0]

    # 2) semantic_model_name: "initial catalog" value from the connection string
    m = re.search(r'initial catalog=([^;]+)', conn_str, re.IGNORECASE)
    semantic_model_name = m.group(1) if m else None

    # 3) semantic_model_id: takes directly from the pbiModelDatabaseName field
    semantic_model_id = model_id

    return {
        'workspace_name': workspace_name,
        'semantic_model_name': semantic_model_name,
        'semantic_model_id': semantic_model_id,
    }


def find_and_replace(path: str, find_and_replace: dict) -> None:
    r"""
    Deploys an item to a specified workspace.

    Args:
        path (str): The source path of the item to be performed.
        find_and_replace (dict): A dictionary where keys are tuples containing a file filter regex and a find regex,
        and values are the replacement strings.

    Returns:
        None

    Raises:
        FileNotFoundError: If the specified path does not exist.

    Examples:
        ```python
        find_and_replace('/path/to/directory', {
            (r'.*\.txt$', r'old_value'): 'new_value',
            (r'.*\.json$', r'"old_key": "old_value"'): '"new_key": "new_value"'
        })
        # This will search for 'old_value' in all .txt files and '"old_key": "old_value"' in all .json files
        # and replace them with 'new_value' and '"new_key": "new_value"' respectively.
        ```
    """
    # Loop through all files and apply the find & replace with regular expressions
    if find_and_replace:
        for root, _, files in os.walk(path):
            for file in files:
                file_path = os.path.join(root, file)
                with open(
                    file_path, 'r', encoding='utf-8', errors='replace'
                ) as file:
                    text = file.read()

                # Loop parameters and execute the find & replace in the ones that match the file path
                for key, replace_value in find_and_replace.items():
                    find_and_replace_file_filter = key[0]
                    find_and_replace_file_find = key[1]

                    if re.search(find_and_replace_file_filter, file_path):
                        text, count_subs = re.subn(
                            find_and_replace_file_find, replace_value, text
                        )

                        if count_subs > 0:
                            logger.info(
                                f"Find & replace in file '{file_path}' with regex '{find_and_replace_file_find}'"
                            )
                            with open(
                                file_path, 'w', encoding='utf-8'
                            ) as file:
                                file.write(text)


def load_and_sanitize(path: str) -> dict:
    """
    Loads and sanitizes a JSON file, particularly useful for Power BI model.json files.
    Tries json5 first for complex content, then falls back to standard json.

    Args:
        path (str): The file path to the JSON file.

    Returns:
        dict: The contents of the JSON file.

    Examples:
        ```python
        load_and_sanitize('dataflow/model.json')
        ```
    """
    try:
        with open(path, 'r', encoding='utf-8-sig') as f:
            data = json5.load(f)
        logger.info(f'Loaded JSON file with json5: {path}')
    except (ImportError, json5.JSONError, FileNotFoundError) as e:
        try:
            # Fallback to standard json
            with open(path, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            logger.info(f'Loaded JSON file with standard json: {path}')
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.error(f'Error reading JSON file: {e}')
            return {}
    return data


def write_single_line_json(data: dict, path: str) -> None:
    """
    Writes the given data to a JSON file at the specified path in single-line format.
    This format matches what Power BI portal exports for dataflows.

    Args:
        data (dict): The data to be written to the JSON file.
        path (str): The file path where the JSON should be saved.

    Returns:
        None

    Examples:
        ```python
        write_single_line_json({'key': 'value'}, 'output.json')
        ```
    """
    if not os.path.exists(os.path.dirname(path)):
        os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w', encoding='utf-8') as file:
        json.dump(data, file, ensure_ascii=False, separators=(',', ':'))


def _flatten_json(data, parent_key='', sep='_'):
    """
    Helper function to flatten nested JSON.

    Args:
        data (dict): JSON to flatten.
        parent_key (str): Parent key (used for recursion).
        sep (str): Separator for flattened keys.

    Returns:
        list[dict]: List of flattened dictionaries.
    """
    items = []
    for k, v in data.items():
        new_key = f'{parent_key}{sep}{k}' if parent_key else k
        if isinstance(v, dict):
            items.extend(_flatten_json(v, new_key, sep=sep).items())
        else:
            items.append((new_key, v))
    return dict(items)


def json_to_df(data: dict | list) -> DataFrame:
    """
    Converts various types of JSON to a pandas.DataFrame.

    Args:
        data (dict | list): The JSON to be converted. Can be a simple dictionary,
        a nested dictionary, or a list of dictionaries.

    Returns:
        pd.DataFrame: The resulting DataFrame.

    Examples:
        ```python
        json_to_df({'key1': 'value1', 'key2': 'value2'})
        json_to_df([{'key1': 'value1'}, {'key2': 'value2'}])
        ```
    """
    if not data:
        return None

    if isinstance(data, dict):

        # If it"s a simple dictionary
        if all(not isinstance(v, (dict, list)) for v in data.values()):
            return pandas.DataFrame([data])

        # If it"s a dictionary with nested levels
        else:
            flattened_data = _flatten_json(data)
            return pandas.DataFrame([flattened_data])

    elif isinstance(data, list):

        # If it"s a list of dictionaries
        if all(isinstance(item, dict) for item in data):
            flattened_list = [_flatten_json(item) for item in data]
            return pandas.DataFrame(flattened_list)
        else:
            raise ValueError(
                'The list contains items that are not dictionaries.'
            )

    else:
        raise TypeError(
            'Input type must be a dictionary or a list of dictionaries.'
        )


def dataframe_to_list(df: DataFrame) -> list[dict]:
    """
    Converts a pandas DataFrame to a list of dictionaries.

    Args:
        df (DataFrame): The DataFrame to convert.

    Returns:
        list[dict]: The resulting list of dictionaries.
    """
    if df is None or df.empty:
        return []

    return df.to_dict(orient='records')


def list_paths_of_type(
    path: Union[str, Path], type: str
) -> List[Union[str, Path]]:
    """
    Returns a list of paths given a type of the items
    """
    paths = glob.glob(f'{path}/**/*.{type}', recursive=True)
    return [str(Path(p).as_posix()) for p in paths]


def extract_middle_path(
    path: str, start_path: Optional[str] = None
) -> Union[str, None]:
    """
    Extract the middle of a full path given a start.
    """
    path_list = path.split('/')[:-1]
    if len(path_list) == 0:
        return None

    middle_path = '/'.join(path_list)

    if start_path is None:
        return middle_path
    else:
        try:
            middle_path = middle_path.split(start_path + '/')[1]
            return middle_path
        except:
            return None


def extract_display_name_from_platform(path: str) -> str:
    with open(Path(path) / '.platform', 'r', encoding='utf-8') as f:
        platform_dict = json.load(f)

    return platform_dict.get('metadata').get('displayName')
