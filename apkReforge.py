#!/usr/bin/env python3
"""
Lautaro D. Villarreal Culic'
apkReforge - Automated APK Rebuild, Align, Sign & Install Tool
"""

import argparse
import subprocess
import sys
import os
import logging
import shutil
import tempfile
import re
from pathlib import Path
from typing import Optional, Dict, List

__version__ = "1.1.2"

class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

class APKReforge:
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.setup_logging()
        self.temp_dir = None
        self.android_debug_keystore = self.get_android_debug_keystore_path()

    def setup_logging(self):
        level = logging.DEBUG if self.verbose else logging.INFO
        logger = logging.getLogger()
        logger.setLevel(level)

        console_handler = logging.StreamHandler()
        formatter = logging.Formatter(
            f'{Colors.YELLOW}%(levelname)s{Colors.RESET}: %(message)s'
        )
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        self.logger = logger

    def get_android_debug_keystore_path(self) -> str:
        home = os.path.expanduser("~")
        return os.path.join(home, ".android", "debug.keystore")

    def check_dependencies(self) -> Dict[str, bool]:
        # Check if required binaries are present and where they're located
        tools = ['apktool', 'zipalign', 'apksigner', 'adb', 'keytool']
        deps = {}

        for tool in tools:
            path = shutil.which(tool)
            if path:
                deps[tool] = True
                if self.verbose:
                    self.logger.debug(f"{tool} found at {path}")
                    if '/usr/bin/' not in path:
                        self.logger.warning(f"{Colors.YELLOW}{tool} is not in /usr/bin/: {path}{Colors.RESET}")
            else:
                deps[tool] = False
                self.logger.error(f"{Colors.RED}Missing tool: {tool}{Colors.RESET}")

        return deps

    def _check_zipalign_fallback(self) -> bool:
        try:
            result = subprocess.run(
                ['zipalign'],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=3
            )
            return 'Usage:' in result.stderr or 'alignment' in result.stdout
        except Exception:
            return False

    def run_command(self, cmd: List[str], error_msg: str = "Command failed") -> bool:
        self.logger.debug(f"$ {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=120
            )
            if self.verbose:
                if result.stdout:
                    self.logger.debug(f"STDOUT:\n{result.stdout}")
                if result.stderr:
                    self.logger.debug(f"STDERR:\n{result.stderr}")

            if result.returncode != 0:
                self.logger.error(f"{Colors.RED}{error_msg} (code {result.returncode}){Colors.RESET}")
                if result.stderr:
                    self.logger.error(result.stderr.strip())
                return False

            return True

        except subprocess.TimeoutExpired as te:
            self.logger.error(f"{Colors.RED}Timeout exceeded: {te}{Colors.RESET}")
            return False
        except Exception as e:
            self.logger.error(f"{Colors.RED}Unexpected error: {str(e)}{Colors.RESET}")
            return False

    def rebuild_apk(self, input_dir: str, output_apk: str) -> bool:
        self.logger.info(f"\n{Colors.BOLD}{Colors.BLUE}[+] PHASE 1: Rebuilding APK{Colors.RESET}")
        if not os.path.exists(os.path.join(input_dir, "AndroidManifest.xml")):
            self.logger.error(f"{Colors.RED}Directory does not contain AndroidManifest.xml{Colors.RESET}")
            return False
        cmd = [
            'apktool', 'b', 
            '-o', output_apk,
            '--use-aapt2' if self.detect_high_sdk(input_dir) else '',
            input_dir
        ]
        cmd = [c for c in cmd if c]
        if not self.run_command(cmd, "Error in apktool"):
            self.logger.warning(f"{Colors.YELLOW}Trying without AAPT2...{Colors.RESET}")
            cmd_fallback = ['apktool', 'b', input_dir, '-o', output_apk]
            return self.run_command(cmd_fallback, "Error in rebuild")
        self.logger.info(f"{Colors.GREEN}Rebuilded APK: {os.path.basename(output_apk)}{Colors.RESET}")
        return True

    def align_apk(self, input_apk: str, output_apk: str) -> bool:
        self.logger.info(f"\n{Colors.BOLD}{Colors.BLUE}[+] PHASE 2: Aligning APK{Colors.RESET}")
        if not self.run_command(
            ['zipalign', '-v', '4', input_apk, output_apk],
            "Error in zipalign"
        ):
            return False
        self.logger.info(f"{Colors.CYAN}Checking alignment...{Colors.RESET}")
        if self.run_command(['zipalign', '-c', '4', output_apk], "Incorrect alignment"):
            self.logger.info(f"{Colors.GREEN}Alignment verified correctly{Colors.RESET}")
            return True
        return False

    def sign_apk(self, input_apk: str, output_apk: str, keystore_path: Optional[str] = None) -> bool:
        self.logger.info(f"\n{Colors.BOLD}{Colors.BLUE}[+] PHASE 3: Signing APK{Colors.RESET}")
        keystore_path = keystore_path or self.get_keystore()
        if not keystore_path:
            return False
        self.logger.info(f"{Colors.CYAN}Using keystore: {os.path.basename(keystore_path)}{Colors.RESET}")
        cmd = [
            'apksigner', 'sign',
            '--ks', keystore_path,
            '--ks-pass', 'pass:android', #################### CHANGE FOR YOUR PASSWORD
            '--ks-key-alias', 'androiddebugkey', #################### CHANGE FOR YOUR ALIAS
            '--key-pass', 'pass:android', #################### CHANGE FOR YOUR PASSWORD
            '--out', output_apk,
            input_apk
        ]
        if not self.run_command(cmd, "Error in signature"):
            return False
        self.logger.info(f"{Colors.CYAN}Verifying signature...{Colors.RESET}")
        if self.run_command(['apksigner', 'verify', output_apk], "Failed signature verification"):
            self.logger.info(f"{Colors.GREEN}Signature verified correctly{Colors.RESET}")
            return True
        return False

    def get_keystore(self) -> Optional[str]:
        if os.path.exists(self.android_debug_keystore):
            return self.android_debug_keystore
        self.logger.info(f"{Colors.YELLOW}Creating temporary keystore...{Colors.RESET}")
        keystore_path = os.path.join(tempfile.gettempdir(), 'apkreforge.keystore')
        cmd = [
            'keytool', '-genkey', '-v',
            '-keystore', keystore_path,
            '-alias', 'androiddebugkey',
            '-keyalg', 'RSA',
            '-keysize', '2048',
            '-validity', '10000',
            '-storepass', 'android',
            '-keypass', 'android',
            '-dname', 'CN=Android Debug,O=Android,C=US'
        ]
        if self.run_command(cmd, "Error creating keystore"):
            return keystore_path
        self.logger.error(f"{Colors.RED}Could not create keystore{Colors.RESET}")
        return None

    def detect_high_sdk(self, input_dir: str) -> bool:
        manifest = os.path.join(input_dir, 'AndroidManifest.xml')
        if not os.path.exists(manifest):
            return False
        try:
            with open(manifest, 'r') as f:
                content = f.read()
            match = re.search(r'targetSdkVersion\s*=\s*"(\d+)"', content)
            if match:
                return int(match.group(1)) >= 34
        except Exception:
            pass
        return False

    def install_apk(self, apk_path: str) -> bool:
        self.logger.info(f"\n{Colors.BOLD}{Colors.BLUE}[+] PHASE 4: Installing APK{Colors.RESET}")
        self.logger.info(f"{Colors.CYAN}Searching for devices...{Colors.RESET}")
        devices = subprocess.run(
            ['adb', 'devices'],
            stdout=subprocess.PIPE,
            text=True
        ).stdout.splitlines()
        active_devices = [d.split('\t')[0] for d in devices[1:] if '\tdevice' in d]
        if not active_devices:
            self.logger.error(f"{Colors.RED}No connected devices found{Colors.RESET}")
            return False
        self.logger.info(f"{Colors.GREEN}Devices detected: {', '.join(active_devices)}{Colors.RESET}")
        success = True
        for device in active_devices:
            self.logger.info(f"{Colors.CYAN}Installing in {device}...{Colors.RESET}")
            cmd = ['adb', '-s', device, 'install', '-r', apk_path]
            if not self.run_command(cmd, f"Error installing in {device}"):
                success = False
        return success

    def cleanup(self):
        if self.temp_dir and os.path.exists(self.temp_dir):
            try:
                shutil.rmtree(self.temp_dir)
                self.logger.debug(f"Temporary directory deleted: {self.temp_dir}")
            except Exception as e:
                self.logger.error(f"Error clearing temporary: {str(e)}")

    def process_apk(self, input_dir: str, output_apk: str, install: bool = False, 
                   keystore: Optional[str] = None) -> bool:
        print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*50}{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.RED}Lautaro Villarreal Culic' - https://lautarovculic.com{Colors.RESET}")
        print(f"{Colors.BOLD}{Colors.RED}RUNNING apkReforge v{__version__}{Colors.RESET}")
        print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*50}{Colors.RESET}")
        self.logger.info(f"{Colors.BOLD}{Colors.CYAN}> INPUT: {input_dir}{Colors.RESET}")
        self.logger.info(f"{Colors.BOLD}{Colors.CYAN}< OUTPUT: {output_apk}{Colors.RESET}")
        deps = self.check_dependencies()
        if missing := [t for t, v in deps.items() if not v]:
            self.logger.error(f"{Colors.RED}[!!!] Missing dependencies: {', '.join(missing)}{Colors.RESET}")
            return False
        self.temp_dir = tempfile.mkdtemp(prefix='apkreforge_')
        self.logger.debug(f"Temporary directory: {self.temp_dir}")
        try:
            rebuilt_apk = os.path.join(self.temp_dir, 'unsigned.apk')
            aligned_apk = os.path.join(self.temp_dir, 'aligned.apk')
            steps = [
                (f"Failed rebuild", lambda: self.rebuild_apk(input_dir, rebuilt_apk)),
                (f"Failed alignment", lambda: self.align_apk(rebuilt_apk, aligned_apk)),
                (f"Failed signature", lambda: self.sign_apk(aligned_apk, output_apk, keystore)),
            ]
            for error_msg, step in steps:
                if not step():
                    self.logger.error(f"{Colors.RED}{error_msg}{Colors.RESET}")
                    return False
            if install and not self.install_apk(output_apk):
                self.logger.warning(f"{Colors.YELLOW}Installation failed, but APK generated{Colors.RESET}")
            self.logger.info(f"\n{Colors.GREEN}[+] PROCESS SUCCESSFULLY COMPLETED!{Colors.RESET}")
            self.logger.info(f"{Colors.GREEN}Final APK: {os.path.abspath(output_apk)}{Colors.RESET}")
            return True
        except Exception as e:
            self.logger.exception(f"{Colors.RED}CRITICAL ERROR: {str(e)}{Colors.RESET}")
            return False
        finally:
            self.cleanup()

def main():
    parser = argparse.ArgumentParser(
        description='apkReforge - Automation for rebuild, align, sign and install of APKs',
        formatter_class=argparse.RawTextHelpFormatter,
        epilog="""Examples:
  apkReforge.py -i ./my_app/ -o final_app.apk
  apkReforge.py -i ./my_app/ -o final_app.apk --install -v
  apkReforge.py -i ./my_app/ -o final_app.apk --keystore my_keystore.jks
        """
    )
    parser.add_argument('-i', '--input', required=True, help='Directory with decompiled APK')
    parser.add_argument('-o', '--output', required=True, help='Final APK path')
    parser.add_argument('--install', action='store_true', help='Install on device after building')
    parser.add_argument('--keystore', help='Custom keystore (default: debug.keystore)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Detailed mode (debug)')
    parser.add_argument('--version', action='version', version=f'apkReforge {__version__}')
    args = parser.parse_args()
    if not os.path.isdir(args.input):
        print(f"{Colors.RED}ERROR: Directory not found: {args.input}{Colors.RESET}")
        return 1
    output_dir = os.path.dirname(args.output) or '.'
    os.makedirs(output_dir, exist_ok=True)
    reforger = APKReforge(verbose=args.verbose)
    success = reforger.process_apk(
        input_dir=os.path.abspath(args.input),
        output_apk=os.path.abspath(args.output),
        install=args.install,
        keystore=args.keystore
    )
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())
