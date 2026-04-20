import os
import sys
import subprocess
import argparse
import json
from pathlib import Path
from datetime import datetime
import difflib
import hashlib


class ConformanceTest:
    
    def __init__(self, build_dir, test_dir, verbose=False):
      
        self.build_dir = Path(build_dir).resolve()
        self.test_dir = Path(test_dir).resolve()
        self.verbose = verbose
        self.qa_dir = Path(__file__).parent.resolve()
        self.script_dir = self.qa_dir
        
        self.reference_dir = self.qa_dir / "conformance_reference"
        self.output_dir = self.qa_dir / "conformance_output"
        self.report_dir = self.qa_dir / "conformance_reports"
        self.expected_dir = self.qa_dir / "conformance_expected"
        
        for d in [self.reference_dir, self.output_dir, self.report_dir, self.expected_dir]:
            d.mkdir(parents=True, exist_ok=True)
        
        self.results = {
            'timestamp': datetime.now().isoformat(),
            'tests': {},
            'summary': {}
        }
    
    def find_parabix_tool(self, tool_name):
        possible_paths = [
            self.build_dir / "bin" / tool_name,
            self.build_dir / "bin" / f"{tool_name}.exe",  # Windows
            self.build_dir / tool_name,
        ]
        
        for path in possible_paths:
            if path.exists() and os.access(path, os.X_OK):
                return path
        
        return None
    
    
    def run_parabix_tool(self, tool_path, input_file, output_file):
        try:
            with open(input_file, 'rb') as infile:
                with open(output_file, 'wb') as outfile:
                    result = subprocess.run(
                        [str(tool_path), str(input_file)],
                        stdout=outfile,
                        stderr=subprocess.PIPE,
                        timeout=30
                    )
            
            if result.returncode != 0:
                if self.verbose:
                    print(f"ERROR: Tool execution failed:")
                    print(result.stderr.decode('utf-8', errors='replace'))
                return False
            
            if self.verbose:
                print(f"✓ Tool output: {output_file}")
            
            return True
            
        except subprocess.TimeoutExpired:
            print(f"ERROR: Tool execution timeout for {input_file}")
            return False
        except Exception as e:
            print(f"ERROR: {e}")
            return False
    
    def compare_files(self, file1, file2):
        try:
            with open(file1, 'rb') as f1, open(file2, 'rb') as f2:
                bytes1 = f1.read()
                bytes2 = f2.read()
            
            if bytes1 == bytes2:
                return True, {'status': 'match', 'size': len(bytes1)}
            else:
                # Try to decode as UTF-8 for diff
                try:
                    text1 = bytes1.decode('utf-8', errors='replace')
                    text2 = bytes2.decode('utf-8', errors='replace')
                    diff = list(difflib.unified_diff(
                        text1.splitlines(keepends=True),
                        text2.splitlines(keepends=True),
                        fromfile=str(file1),
                        tofile=str(file2),
                        lineterm=''
                    ))
                    diff_text = ''.join(diff[:20])  # Limit to first 20 lines
                except:
                    diff_text = "Binary files differ"
                
                return False, {
                    'status': 'mismatch',
                    'size_parabix': len(bytes1),
                    'size_reference': len(bytes2),
                    'diff': diff_text
                }
        except Exception as e:
            return False, {'error': str(e)}
    
    def test_form(self, form, input_files=None):
        print(f"\n{'='*70}")
        print(f"Testing {form.upper()} Normalization Form")
        print(f"{'='*70}")
        
        tool_path = self.find_parabix_tool(form)
        if not tool_path:
            print(f"ERROR: parabix {form} tool not found in {self.build_dir}")
            return None
        
        print(f"Using parabix tool: {tool_path}")
        
        if not input_files:
            if not self.test_dir.exists():
                print(f"ERROR: Test directory not found: {self.test_dir}")
                return None
            input_files = sorted(self.test_dir.glob('*'))
            # Filter out directories
            input_files = [f for f in input_files if f.is_file()]
        
        if not input_files:
            print(f"WARNING: No input files found in {self.test_dir}")
            return None
        
        print(f"Found {len(input_files)} test files")
        
        form_results = {
            'form': form.upper(),
            'tool_path': str(tool_path),
            'tests': {},
            'passed': 0,
            'failed': 0,
        }
        
        for input_file in input_files:
            filename = input_file.name
            test_name = f"{form}_{filename}"
            
            expected_file = self.expected_dir / f"{filename}.{form}.expected"
            if not expected_file.exists():
                form_results['tests'][test_name] = {
                    'status': 'error',
                    'error': f'Expected output not found: {expected_file}'
                }
                form_results['failed'] += 1
                print(f"ERROR: Missing expected output: {expected_file}")
                continue
            ref_file = expected_file
            if self.verbose:
                print(f"✓ Using expected: {expected_file}")

            out_file = self.output_dir / f"{filename}.{form}"
            if not self.run_parabix_tool(tool_path, input_file, out_file):
                form_results['tests'][test_name] = {
                    'status': 'error',
                    'error': 'Tool execution failed'
                }
                form_results['failed'] += 1
                continue

            match, diff_info = self.compare_files(out_file, ref_file)
            
            status = 'PASS' if match else 'FAIL'
            print(f"  {status}: {filename}")
            
            if not match and self.verbose:
                if 'diff' in diff_info:
                    print(f"    Diff:\n{diff_info['diff']}")
                else:
                    print(f"    Sizes: Parabix={diff_info.get('size_parabix', 'N/A')}, Reference={diff_info.get('size_reference', 'N/A')}")
            
            form_results['tests'][test_name] = {
                'status': 'pass' if match else 'fail',
                'input_file': filename,
                'diff_info': diff_info
            }
            
            if match:
                form_results['passed'] += 1
            else:
                form_results['failed'] += 1
        
        return form_results
    
    def run_tests(self, forms=['nfc', 'nfd'], input_files=None):
       
        print(f"\nParabix Unicode Normalization Conformance Test")
        print(f"Build directory: {self.build_dir}")
        print(f"Test directory: {self.test_dir}")
        print(f"Comparison: precomputed expected outputs only")
        
        self.results['tests'] = {}
        total_passed = 0
        total_failed = 0
        
        for form in forms:
            result = self.test_form(form, input_files)
            if result:
                self.results['tests'][form] = result
                total_passed += result['passed']
                total_failed += result['failed']
        
        self.results['summary'] = {
            'total_passed': total_passed,
            'total_failed': total_failed,
            'total_tests': total_passed + total_failed,
            'pass_rate': f"{100*total_passed/(total_passed+total_failed):.1f}%" if total_passed+total_failed > 0 else "N/A"
        }
        
        print(f"\n{'='*70}")
        print("SUMMARY")
        print(f"{'='*70}")
        print(f"Total Tests: {self.results['summary']['total_tests']}")
        print(f"Passed: {total_passed}")
        print(f"Failed: {total_failed}")
        print(f"Pass Rate: {self.results['summary']['pass_rate']}")
        
        return self.results
    
    def save_report(self, filename=None):
        if not filename:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = self.report_dir / f"conformance_report_{timestamp}.json"
        else:
            filename = self.report_dir / filename
        
        with open(filename, 'w') as f:
            json.dump(self.results, f, indent=2)
        
        print(f"\nReport saved: {filename}")
        return filename


def main():
    parser = argparse.ArgumentParser(
        description='Parabix Unicode Normalization Conformance Testing'
    )
    parser.add_argument('--build_dir', default='./build',
                       help='Path to parabix build directory')
    parser.add_argument('--test_dir', default='./QA/Normalization',
                       help='Directory with test input files')
    parser.add_argument('--nfc', action='store_true', help='Test NFC form')
    parser.add_argument('--nfd', action='store_true', help='Test NFD form')
    parser.add_argument('--both', action='store_true', 
                       help='Test both NFC and NFD (default)')
    parser.add_argument('--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--input_file', 
                       help='Test single input file')
    
    args = parser.parse_args()
    
    if args.nfc:
        forms = ['nfc']
    elif args.nfd:
        forms = ['nfd']
    else:
        forms = ['nfc', 'nfd']
 
    tester = ConformanceTest(args.build_dir, args.test_dir, args.verbose)

    input_files = None
    if args.input_file:
        input_files = [Path(args.input_file)]
    
    results = tester.run_tests(forms, input_files)

    report_path = tester.save_report()
 
    if results['summary']['total_failed'] > 0:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == '__main__':
    main()
