#!/usr/bin/env python3
"""
Pipeline Compliance Validator

Validates that all required components for the 0160 auto-fix pipeline are present
and correctly configured. This is the main entry point for CI/pre-push validation.
"""

import sys
import argparse
import subprocess
from pathlib import Path
from typing import List, Tuple, Dict

# Required files and their descriptions
REQUIRED_FILES = {
    "PIPELINE_CONTRACT.md": "Pipeline contract documentation",
    "PIPELINE_CONTRACT_v2.md": "Pipeline contract v2 documentation",
    "PIPELINE_CONTRACT_IMPROVEMENTS.md": "Pipeline contract improvements",
    "tools/auto_fix_0160_loop.py": "Main auto-fix loop script",
    "tools/send_sirecepde.py": "SIFEN submission script",
    "tools/follow_lote.py": "Lote status tracking script",
    "tools/validate_success_criteria.py": "Success criteria validation",
    "tools/add_fix_summary.py": "Fix summary generator",
    "docs/aprendizajes/anti-regresion.md": "Anti-regression rules",
}

# Required CLI flags
REQUIRED_FLAGS = {
    "auto_fix_0160_loop.py": ["--poll-every", "--max-poll"],
    "send_sirecepde.py": ["--env", "--xml", "--bump-doc", "--dump-http", "--artifacts-dir", "--iteration"],
}


def check_file_exists(path: Path) -> Tuple[bool, str]:
    """Check if a file exists."""
    if path.exists():
        return True, "✓ Found"
    return False, "✗ Missing"


def check_help_flags(script_path: Path, required_flags: List[str], verbose: bool = False) -> Tuple[bool, str]:
    """Check if script help shows required flags."""
    try:
        # Use .venv/bin/python explicitly with -m module syntax for tools
        python_exe = Path(".venv/bin/python")
        if not python_exe.exists():
            python_exe = Path(sys.executable)
        
        # Convert tools/script.py to -m tools.script
        script_str = str(script_path)
        if script_str.startswith("tools/") and script_str.endswith(".py"):
            module_name = script_str.replace("/", ".").replace(".py", "")
            cmd = [str(python_exe), "-m", module_name, "--help"]
        else:
            cmd = [str(python_exe), script_str, "--help"]
            
        # Run from current directory (tesaka-cv)
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            cwd=".",  # Explicitly set current directory
        )
        if result.returncode != 0:
            if verbose:
                print(f"    Debug: cmd={' '.join(cmd)}")
                print(f"    Debug: returncode={result.returncode}")
                print(f"    Debug: stderr={result.stderr}")
            return False, "✗ Failed to run --help"

        help_text = result.stdout + result.stderr
        missing_flags = []
        for flag in required_flags:
            if flag not in help_text:
                missing_flags.append(flag)

        if missing_flags:
            return False, f"✗ Missing flags: {', '.join(missing_flags)}"
        return True, "✓ All required flags present"

    except subprocess.TimeoutExpired:
        return False, "✗ Timeout running --help"
    except Exception as e:
        return False, f"✗ Error: {e}"


def validate_pipeline(verbose: bool = False) -> Tuple[int, Dict[str, str]]:
    """Validate all pipeline components."""
    results = {}
    score = 0
    max_score = len(REQUIRED_FILES) + len(REQUIRED_FLAGS)

    print("🔍 Pipeline Compliance Validator")
    print("=" * 50)

    # Check required files
    print("\n📁 Required Files:")
    for file_path, description in REQUIRED_FILES.items():
        path = Path(file_path)
        exists, msg = check_file_exists(path)
        results[file_path] = msg
        if verbose:
            print(f"  {file_path:<40} {msg}")
        else:
            print(f"  {msg:<20} {file_path}")
        if exists:
            score += 1

    # Check required CLI flags
    print("\n⚙️  Required CLI Flags:")
    for script, flags in REQUIRED_FLAGS.items():
        exists, msg = check_help_flags(Path(script), flags, verbose=verbose)
        key = f"{script}_flags"
        results[key] = msg
        if verbose:
            print(f"  {script:<40} {msg}")
        else:
            print(f"  {msg:<20} {script}")
        if exists:
            score += 1

    # Calculate score
    print("\n📊 Summary:")
    print(f"  Score: {score}/{max_score}")
    percentage = (score / max_score) * 100
    print(f"  Compliance: {percentage:.1f}%")

    if score == max_score:
        print("\n✅ Pipeline is READY for use")
        return 0, results
    else:
        print("\n❌ Pipeline is NOT ready")
        print("\nMissing components must be addressed before proceeding.")
        return 1, results


def main():
    parser = argparse.ArgumentParser(description="Validate pipeline compliance")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--score-only", action="store_true", help="Only show score percentage")
    args = parser.parse_args()

    exit_code, results = validate_pipeline(verbose=args.verbose)

    if args.score_only:
        # Calculate percentage from results
        passed = sum(1 for v in results.values() if v.startswith("✓"))
        total = len(results)
        percentage = (passed / total) * 100
        print(f"{percentage:.1f}%")
        sys.exit(exit_code)

    sys.exit(exit_code)


if __name__ == "__main__":
    main()
