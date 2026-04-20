import sys
import subprocess
import argparse
import json
from pathlib import Path
from datetime import datetime
import unicodedata

class OfficialConformanceTest:
    
    def __init__(self, build_dir: Path, test_suite_dir: Path, verbose: bool = False):
      
        self.build_dir = Path(build_dir).resolve()
        self.test_suite_dir = Path(test_suite_dir).resolve()
        self.verbose = verbose
        self.qa_dir = Path(__file__).parent.resolve()
        
        self.report_dir = self.qa_dir / "conformance_reports"
        self.report_dir.mkdir(parents=True, exist_ok=True)
        
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'test_suite': 'Unicode Official Normalization Test Suite',
            'tests': {},
            'summary': {}
        }
    
    def find_parabix_tool(self, tool_name: str) -> Path:
        possible_paths = [
            self.build_dir / "bin" / tool_name,
            self.build_dir / "bin" / f"{tool_name}.exe",
            self.build_dir / tool_name,
        ]
        
        for path in possible_paths:
            if path.exists() and path.is_file():
                return path
        
        return None
    
    def run_parabix_tool(self, tool_path: Path, input_text: str) -> str:
        try:
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', delete=False, suffix='.txt') as f:
                f.write(input_text)
                temp_input = f.name
            
            result = subprocess.run(
                [str(tool_path), temp_input],
                capture_output=True,
                timeout=10
            )
            
            if result.returncode != 0:
                if self.verbose:
                    print(f"Tool error: {result.stderr.decode('utf-8', errors='replace')}")
                return None
         
            import os
            os.unlink(temp_input)
            
            return result.stdout.decode('utf-8', errors='replace')
            
        except subprocess.TimeoutExpired:
            if self.verbose:
                print(f"Tool timeout")
            return None
        except Exception as e:
            if self.verbose:
                print(f"Tool error: {e}")
            return None
    
    def test_single_case(self, test_num: int, input_text: str, expected_text: str, 
                        tool_path: Path, form: str) -> dict:
        result = {
            'test_num': test_num,
            'form': form.upper(),
            'status': 'pass',
            'input_codepoints': ' '.join(f"U+{ord(c):04X}" for c in input_text),
            'expected_codepoints': ' '.join(f"U+{ord(c):04X}" for c in expected_text),
        }

        parabix_output = self.run_parabix_tool(tool_path, input_text)
        if parabix_output is None:
            result['status'] = 'error'
            result['error'] = 'Tool execution failed'
            return result
        
        parabix_output = parabix_output.rstrip('\n\r')
        
        if parabix_output == expected_text:
            result['status'] = 'pass'
        else:
            result['status'] = 'fail'
            result['parabix_output'] = repr(parabix_output)
            result['parabix_codepoints'] = ' '.join(f"U+{ord(c):04X}" for c in parabix_output)
       
            for i, (c1, c2) in enumerate(zip(parabix_output, expected_text)):
                if c1 != c2:
                    result['first_diff_pos'] = i
                    result['first_diff_parabix'] = f"U+{ord(c1):04X} ({unicodedata.name(c1, 'UNKNOWN')})"
                    result['first_diff_expected'] = f"U+{ord(c2):04X} ({unicodedata.name(c2, 'UNKNOWN')})"
                    break
            
            if len(parabix_output) != len(expected_text):
                result['output_length_mismatch'] = {
                    'parabix': len(parabix_output),
                    'expected': len(expected_text)
                }
        
        return result
    
    def test_form(self, form: str, sample: int = None) -> dict:
        print(f"\n{'='*80}")
        print(f"Testing {form.upper()} Normalization (Official Unicode Test Suite)")
        print(f"{'='*80}")
        
        tool_path = self.find_parabix_tool(form)
        if not tool_path:
            print(f"ERROR: {form} tool not found in {self.build_dir}")
            return None
        
        print(f"Using tool: {tool_path}")

        test_files = sorted(self.test_suite_dir.glob('unicode_tests_*.txt'))
        
        if not test_files:
            print(f"ERROR: No saved official test files found in {self.test_suite_dir}")
            print(f"  Run: python3 unicode_official_tests.py --download --parse --save_cases")
            return None
        
        saved_form_file = self.test_suite_dir / f"unicode_tests_{form}.txt"
        if not saved_form_file.exists():
            print(f"ERROR: Expected saved file for form {form.upper()} not found: {saved_form_file}")
            print(f"  Run: python3 unicode_official_tests.py --download --parse --save_cases")
            return None
        
        print(f"Found official saved test file: {saved_form_file.name}")
        
        form_results = {
            'form': form.upper(),
            'tool_path': str(tool_path),
            'test_count': 0,
            'passed': 0,
            'failed': 0,
            'errors': 0,
            'tests': {}
        }
        
        try:
            with open(saved_form_file, 'r', encoding='utf-8') as f:
                lines = [line.rstrip('\n') for line in f if line.strip() and not line.startswith('#')]

            test_cases = []
            for line in lines:
                parts = line.split('\t')
                if len(parts) != 2:
                    continue
                source_text, expected_text = parts
                test_cases.append((source_text, expected_text))

            if sample is not None:
                test_cases = test_cases[:sample]
                print(f"Running sample of {len(test_cases)} test cases for {form.upper()} (limited by --sample)")
            else:
                print(f"Running all {len(test_cases)} test cases for {form.upper()}")

            form_results['test_count'] = len(test_cases)

            for test_index, (input_text, expected_text) in enumerate(test_cases, start=1):
                test_result = self.test_single_case(test_index, input_text, expected_text, tool_path, form)

                if test_result['status'] == 'pass':
                    form_results['passed'] += 1
                elif test_result['status'] == 'fail':
                    form_results['failed'] += 1
                    if self.verbose:
                        print(f"FAIL: Test {test_index}")
                        print(f"  Input: {test_result['input_codepoints']}")
                        print(f"  Expected: {test_result['expected_codepoints']}")
                        print(f"  Got: {test_result['parabix_codepoints']}")
                else:
                    form_results['errors'] += 1
                    if self.verbose:
                        print(f"ERROR: Test {test_index} - {test_result.get('error', 'Unknown error')}")

                if test_result['status'] != 'pass' and len(form_results['tests']) < 10:
                    form_results['tests'][f"test_{test_index}"] = test_result

                if self.verbose and test_index % 500 == 0:
                    print(f"  Progress: {test_index}/{len(test_cases)} tests")

        except Exception as e:
            print(f"ERROR reading saved test cases: {e}")
            return None
        
        total = form_results['passed'] + form_results['failed'] + form_results['errors']
        pass_rate = 100 * form_results['passed'] / total if total > 0 else 0
        
        print(f"\n{form.upper()} Summary:")
        print(f"  Total tests: {total}")
        print(f"  Passed: {form_results['passed']}")
        print(f"  Failed: {form_results['failed']}")
        print(f"  Errors: {form_results['errors']}")
        print(f"  Pass rate: {pass_rate:.1f}%")
        
        return form_results
    
    def run_tests(self, forms: list, sample: int = None) -> dict:
        print("Official Unicode Normalization Conformance Testing")
        print(f"Test Suite: Unicode Official Normalization Test Suite")
        print(f"Build directory: {self.build_dir}")
        print(f"Test data: {self.test_suite_dir}")
        
        for form in forms:
            result = self.test_form(form, sample)
            if result:
                self.results['tests'][form] = result
      
        total_passed = sum(
            r.get('passed', 0) 
            for r in self.results['tests'].values()
        )
        total_failed = sum(
            r.get('failed', 0) 
            for r in self.results['tests'].values()
        )
        total_errors = sum(
            r.get('errors', 0) 
            for r in self.results['tests'].values()
        )
        
        total = total_passed + total_failed + total_errors
        
        self.results['summary'] = {
            'total_passed': total_passed,
            'total_failed': total_failed,
            'total_errors': total_errors,
            'total_tests': total,
            'pass_rate': f"{100*total_passed/total:.1f}%" if total > 0 else "N/A"
        }
        
        print(f"\n{'='*80}")
        print("OVERALL SUMMARY")
        print(f"{'='*80}")
        print(f"Total Tests: {total}")
        print(f"Passed: {total_passed}")
        print(f"Failed: {total_failed}")
        print(f"Errors: {total_errors}")
        print(f"Pass Rate: {self.results['summary']['pass_rate']}")
        
        return self.results
    
    def save_report(self, filename: str = None) -> Path:
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = f"conformance_official_report_{timestamp}.json"
        
        filepath = self.report_dir / filename
        
        with open(filepath, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\nReport saved: {filepath}")
        return filepath


def main():
    parser = argparse.ArgumentParser(
        description='Official Unicode Normalization Conformance Testing'
    )
    parser.add_argument('--build_dir', default='./build',
                       help='Parabix build directory')
    parser.add_argument('--test_suite', default='./QA/unicode_official_tests',
                       help='Directory with official Unicode test files')
    parser.add_argument('--nfc', action='store_true', help='Test NFC form')
    parser.add_argument('--nfd', action='store_true', help='Test NFD form')
    parser.add_argument('--nfkc', action='store_true', help='Test NFKC form')
    parser.add_argument('--nfkd', action='store_true', help='Test NFKD form')
    parser.add_argument('--all', action='store_true', help='Test all forms')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--sample', type=int, default=None,
                       help='Run only first N test cases per form (for quick testing)')
    
    args = parser.parse_args()
    
    if args.all:
        forms = ['nfc', 'nfd', 'nfkc', 'nfkd']
    else:
        forms = []
        if args.nfc:
            forms.append('nfc')
        if args.nfd:
            forms.append('nfd')
        if args.nfkc:
            forms.append('nfkc')
        if args.nfkd:
            forms.append('nfkd')
    
    if not forms:
        forms = ['nfc', 'nfd']  # Default

    tester = OfficialConformanceTest(args.build_dir, args.test_suite, args.verbose)
    results = tester.run_tests(forms, args.sample)
    tester.save_report()

    if results['summary']['total_failed'] > 0 or results['summary']['total_errors'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
