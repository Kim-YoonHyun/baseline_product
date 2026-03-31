#!/usr/bin/env python3
"""
Dependency Synchronization Tool

Analyzes Python source files to identify third-party dependencies and updates
requirements.txt with categorized dependencies.

Features:
- Auto-detects package name from pyproject.toml
- Analyzes all Python files for import statements
- Categorizes dependencies by module
- Updates requirements.txt with proper grouping
- Colored terminal output with graceful fallback
"""

import re
import sys
import tomllib
from argparse import ArgumentParser, Namespace
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Set


# Python standard library modules (Python 3.10+)
STDLIB_MODULES = {
    'abc', 'aifc', 'argparse', 'array', 'ast', 'asynchat', 'asyncio', 'asyncore',
    'atexit', 'audioop', 'base64', 'bdb', 'binascii', 'binhex', 'bisect', 'builtins',
    'bz2', 'calendar', 'cgi', 'cgitb', 'chunk', 'cmath', 'cmd', 'code', 'codecs',
    'codeop', 'collections', 'colorsys', 'compileall', 'concurrent', 'configparser',
    'contextlib', 'contextvars', 'copy', 'copyreg', 'crypt', 'csv', 'ctypes',
    'curses', 'dataclasses', 'datetime', 'dbm', 'decimal', 'difflib', 'dis',
    'distutils', 'doctest', 'email', 'encodings', 'enum', 'errno', 'faulthandler',
    'fcntl', 'filecmp', 'fileinput', 'fnmatch', 'formatter', 'fractions', 'ftplib',
    'functools', 'gc', 'getopt', 'getpass', 'gettext', 'glob', 'graphlib', 'grp',
    'gzip', 'hashlib', 'heapq', 'hmac', 'html', 'http', 'imaplib', 'imghdr', 'imp',
    'importlib', 'inspect', 'io', 'ipaddress', 'itertools', 'json', 'keyword',
    'lib2to3', 'linecache', 'locale', 'logging', 'lzma', 'mailbox', 'mailcap',
    'marshal', 'math', 'mimetypes', 'mmap', 'modulefinder', 'multiprocessing',
    'netrc', 'nis', 'nntplib', 'numbers', 'operator', 'optparse', 'os', 'ossaudiodev',
    'parser', 'pathlib', 'pdb', 'pickle', 'pickletools', 'pipes', 'pkgutil',
    'platform', 'plistlib', 'poplib', 'posix', 'posixpath', 'pprint', 'profile',
    'pstats', 'pty', 'pwd', 'py_compile', 'pyclbr', 'pydoc', 'queue', 'quopri',
    'random', 're', 'readline', 'reprlib', 'resource', 'rlcompleter', 'runpy',
    'sched', 'secrets', 'select', 'selectors', 'shelve', 'shlex', 'shutil', 'signal',
    'site', 'smtpd', 'smtplib', 'sndhdr', 'socket', 'socketserver', 'spwd', 'sqlite3',
    'ssl', 'stat', 'statistics', 'string', 'stringprep', 'struct', 'subprocess',
    'sunau', 'symbol', 'symtable', 'sys', 'sysconfig', 'syslog', 'tabnanny',
    'tarfile', 'telnetlib', 'tempfile', 'termios', 'test', 'textwrap', 'threading',
    'time', 'timeit', 'tkinter', 'token', 'tokenize', 'tomllib', 'trace', 'traceback',
    'tracemalloc', 'tty', 'turtle', 'turtledemo', 'types', 'typing', 'unicodedata',
    'unittest', 'urllib', 'uu', 'uuid', 'venv', 'warnings', 'wave', 'weakref',
    'webbrowser', 'winreg', 'winsound', 'wsgiref', 'xdrlib', 'xml', 'xmlrpc',
    'zipapp', 'zipfile', 'zipimport', 'zlib', '_thread'
}

# Package name normalization mapping
PACKAGE_MAPPING = {
    'git': 'GitPython',
    'sqlalchemy': 'SQLAlchemy',
    'yaml': 'PyYAML',
}

# Package version requirements
PACKAGE_VERSIONS = {
    'numpy': '>=2.0.0',
    'pandas': '>=2.0.0',
    'matplotlib': '>=3.0.0',
    'pymysql': '>=1.1.0',
    'SQLAlchemy': '>=2.0.0',
    'semver': '>=3.0.0',
    'GitPython': '>=3.1.0',
    'openai': '>=2.0.0',
    'openpyxl': '>=3.0.0',
    'xlrd': '>=2.0.0',
}


@dataclass
class ColorScheme:
    """Terminal color codes with graceful fallback."""
    RED: str = '\033[0;31m'
    GREEN: str = '\033[0;32m'
    YELLOW: str = '\033[1;33m'
    BLUE: str = '\033[0;34m'
    NC: str = '\033[0m'  # No Color

    def disable(self):
        """Disable colors for non-TTY environments."""
        self.RED = self.GREEN = self.YELLOW = self.BLUE = self.NC = ''


@dataclass
class AnalysisResult:
    """Container for dependency analysis results."""
    module_deps: Dict[str, Set[str]] = field(default_factory=lambda: defaultdict(set))
    all_deps: Set[str] = field(default_factory=set)

    def get_versioned_deps(self) -> Dict[str, str]:
        """Return dependencies with version specifiers."""
        return {pkg: PACKAGE_VERSIONS.get(pkg, '>=1.0.0') for pkg in sorted(self.all_deps)}


class DependencyAnalyzer:
    """Analyzes Python files to extract third-party dependencies."""

    def __init__(self, package_dir: Path, package_name: str):
        self.package_dir = package_dir
        self.package_name = package_name
        self.import_pattern = re.compile(r'^(?:from\s+(\S+)|import\s+(\S+))(?:\s+|$)')

    def extract_imports(self, file_path: Path) -> Set[str]:
        """Extract top-level imports from a Python file."""
        imports = set()
        try:
            content = file_path.read_text(encoding='utf-8')
            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                match = self.import_pattern.match(line)
                if match:
                    module = match.group(1) or match.group(2)
                    top_level = module.split('.')[0]
                    imports.add(top_level)
        except Exception as e:
            print(f"Warning: Error reading {file_path}: {e}", file=sys.stderr)

        return imports

    def is_third_party(self, package: str) -> bool:
        """Check if a package is third-party (not stdlib or local)."""
        return (
            package not in STDLIB_MODULES
            and not package.startswith(self.package_name)
        )

    def analyze(self) -> AnalysisResult:
        """Analyze all Python files and categorize dependencies."""
        result = AnalysisResult()

        for py_file in self.package_dir.rglob('*.py'):
            # Skip __pycache__ and test files
            if '__pycache__' in str(py_file) or 'test' in py_file.name.lower():
                continue

            # Determine module name from directory structure
            try:
                rel_path = py_file.relative_to(self.package_dir)
                module_name = rel_path.parts[0] if len(rel_path.parts) > 1 else 'core'
            except ValueError:
                continue

            # Extract and filter imports
            imports = self.extract_imports(py_file)
            third_party = {
                self.normalize_package_name(pkg)
                for pkg in imports
                if pkg and self.is_third_party(pkg)
            }

            result.module_deps[module_name].update(third_party)
            result.all_deps.update(third_party)

        return result

    @staticmethod
    def normalize_package_name(package: str) -> str:
        """Normalize package names to PyPI equivalents."""
        return PACKAGE_MAPPING.get(package, package)


class RequirementsWriter:
    """Generates and writes requirements.txt file."""

    def __init__(self, project_root: Path, result: AnalysisResult):
        self.project_root = project_root
        self.result = result
        self.versioned_deps = result.get_versioned_deps()

    def _format_deps(self, *patterns: str) -> str:
        """Format dependencies matching any of the given patterns."""
        matched = []
        for pkg, version in sorted(self.versioned_deps.items()):
            if any(re.match(pattern, pkg) for pattern in patterns):
                matched.append(f"{pkg}{version}")
        return '\n'.join(matched) if matched else ''

    def generate_requirements(self) -> str:
        """Generate requirements.txt content."""
        sections = []

        # Core dependencies
        core_deps = self._format_deps(r'^(numpy|pandas)$')
        if core_deps:
            sections.append(f"# Core dependencies (used by multiple modules)\n{core_deps}")

        # Database utilities
        db_deps = self._format_deps(r'^(pymysql|SQLAlchemy)$')
        if db_deps:
            sections.append(f"# Database utilities (dbutils)\n{db_deps}")

        # Plotting utilities
        plot_deps = self._format_deps(r'^matplotlib$')
        if plot_deps:
            sections.append(f"# Plotting utilities (plotutils)\n{plot_deps}")

        # Version utilities
        version_deps = self._format_deps(r'^(semver|GitPython)$')
        if version_deps:
            sections.append(f"# Version utilities (versionutils)\n{version_deps}")

        # Optional dependencies
        optional_sections = []

        openai_deps = self._format_deps(r'^openai$')
        if openai_deps:
            optional_sections.append(
                f"# LLM features (utils - openai integration, optional)\n{openai_deps}"
            )

        excel_deps = self._format_deps(r'^(openpyxl|xlrd)$')
        if excel_deps:
            optional_sections.append(
                "# File format support (pandas backends for Excel files)\n"
                "# These are not directly imported but used by pandas for read_excel()\n"
                f"{excel_deps}"
            )

        if optional_sections:
            sections.append("# Optional dependencies\n" + '\n\n'.join(optional_sections))

        return '\n\n'.join(sections) + '\n'

    def write(self) -> Path:
        """Write requirements.txt file."""
        requirements_file = self.project_root / 'requirements.txt'
        content = self.generate_requirements()
        requirements_file.write_text(content, encoding='utf-8')
        return requirements_file


def detect_package_info(project_root: Path) -> tuple[str, Path]:
    """
    Auto-detect package name and directory from pyproject.toml or directory structure.

    Returns:
        tuple: (package_name, package_directory)
    """
    pyproject_file = project_root / 'pyproject.toml'

    # Try to read package name from pyproject.toml
    if pyproject_file.exists():
        try:
            with open(pyproject_file, 'rb') as f:
                config = tomllib.load(f)
                package_name = config.get('project', {}).get('name')
                if package_name:
                    package_dir = project_root / package_name
                    if package_dir.exists() and package_dir.is_dir():
                        return package_name, package_dir
        except Exception as e:
            print(f"Warning: Could not parse pyproject.toml: {e}", file=sys.stderr)

    # Fallback: look for directories with __init__.py
    for item in project_root.iterdir():
        if item.is_dir() and not item.name.startswith('.') and item.name not in ['scripts', 'test', 'tests', 'docs', 'build', 'dist']:
            if (item / '__init__.py').exists():
                return item.name, item

    raise FileNotFoundError(
        "Could not auto-detect package directory. "
        "Ensure pyproject.toml exists or package directory contains __init__.py"
    )


def print_header(colors: ColorScheme):
    """Print formatted header."""
    print(f"{colors.BLUE}{'=' * 40}{colors.NC}")
    print(f"{colors.BLUE}  Dependency Synchronization Tool{colors.NC}")
    print(f"{colors.BLUE}{'=' * 40}{colors.NC}\n")


def print_summary(result: AnalysisResult, colors: ColorScheme):
    """Print module dependency summary."""
    print(f"\n{colors.YELLOW}Module Dependencies:{colors.NC}")
    for module, deps in sorted(result.module_deps.items()):
        # Filter out empty strings and sort
        filtered_deps = sorted(d for d in deps if d)
        if filtered_deps:
            deps_str = ', '.join(filtered_deps)
            print(f"  {colors.GREEN}{module}:{colors.NC} {deps_str}")


def get_args() -> Namespace:
    parser = ArgumentParser(
        description='Analyze Python dependencies and update requirements.txt'
    )
    # parser.add_argument(
    #     '--project-root',
    #     type=Path,
    #     help='Project root directory (default: parent of scripts/)'
    # )
    parser.add_argument(
        '--no-color',
        action='store_true',
        help='Disable colored output'
    )
    return parser.parse_args()


def main():
    # args 세팅
    args = get_args()
    scripts_path = Path(__file__).resolve().parent
    print(scripts_path)
    sys.exit()

    # Setup colors
    colors = ColorScheme()
    if args.no_color or not sys.stdout.isatty():
        colors.disable()

    # Determine project root
    if args.project_root:
        project_root = args.project_root.resolve()
    else:
        script_dir = Path(__file__).parent
        project_root = script_dir.parent

    print_header(colors)
    print(f"{colors.YELLOW}Project Root:{colors.NC} {project_root}\n")

    # Auto-detect package information
    try:
        package_name, package_dir = detect_package_info(project_root)
    except FileNotFoundError as e:
        print(f"{colors.RED}Error:{colors.NC} {e}", file=sys.stderr)
        sys.exit(1)

    print(f"{colors.YELLOW}Package Name:{colors.NC} {package_name}")
    print(f"{colors.YELLOW}Source Directory:{colors.NC} {package_dir}\n")

    # Analyze dependencies
    print(f"{colors.YELLOW}Step 1:{colors.NC} Analyzing Python files...")
    analyzer = DependencyAnalyzer(package_dir, package_name)
    result = analyzer.analyze()

    if not result.all_deps:
        print(f"{colors.YELLOW}No third-party dependencies found.{colors.NC}")
        sys.exit(0)

    print(f"{colors.GREEN}✓{colors.NC} Found {len(result.all_deps)} unique dependencies\n")

    # Generate requirements.txt
    print(f"{colors.YELLOW}Step 2:{colors.NC} Generating requirements.txt...")
    writer = RequirementsWriter(project_root, result)
    requirements_file = writer.write()
    print(f"{colors.GREEN}✓{colors.NC} {requirements_file} updated\n")

    # Print summary
    print_summary(result, colors)

    print(f"\n{colors.BLUE}{'=' * 40}{colors.NC}")
    print(f"{colors.BLUE}  Summary{colors.NC}")
    print(f"{colors.BLUE}{'=' * 40}{colors.NC}")
    print(f"{colors.YELLOW}Files updated:{colors.NC}")
    print(f"  • requirements.txt")
    print(f"\n{colors.YELLOW}Total unique dependencies:{colors.NC} {len(result.all_deps)}")
    print(f"\n{colors.GREEN}Done!{colors.NC} Review the changes and commit if satisfied.\n")


if __name__ == '__main__':
    main()
