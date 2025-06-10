# apkReforge v1.1.2

**apkReforge** is an automated tool for rebuilding, aligning, signing, and optionally installing Android APKs. It enhances the standard workflow by validating dependencies, handling keystore generation, and producing clean debug outputs.

---

## Features

- Rebuild APKs using `apktool`
- Align APKs using `zipalign`
- Sign APKs using `apksigner`
- Verify signature and alignment
- Automatically detect `targetSdkVersion` to enable AAPT2
- Optional device installation via `adb`
- Automatic generation of debug keystore if missing
- Color-coded CLI output for better readability

---

## Requirements

- **Python 3.7+**
- **System binaries**:
  - `apktool`
  - `zipalign`
  - `apksigner`
  - `adb`
  - `keytool`


## ATTENTION
These binaries **must be installed and accessible via `/usr/bin/`** or present in your system `$PATH`.

---

## Usage

```bash
python apkReforge.py -i <input_directory> -o <output.apk> [--install] [-v] [--keystore <path>]
```

### Example:

```bash
python apkReforge.py -i ./my_decompiled_apk -o my_rebuilt.apk --install -v
```

### Custom keystore?
Just **change the content in the code**
```python
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
```

---

## Disclaimer

This tool is intended for **ethical hacking, testing, and educational purposes only**. Ensure you have proper authorization before using it against any APK or device.
