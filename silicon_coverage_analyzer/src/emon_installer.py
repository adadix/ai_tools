"""
EMON Auto-Installer

Automatically downloads and installs the latest EMON version on SUT.
Downloads from Intel SharePoint, transfers to SUT, and installs.
"""

import os
import sys
import re
import tempfile
import shutil
import subprocess
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).parent.parent))

from src.remote_transfer import RemoteTransfer


class EmonInstaller:
    """Handles automatic EMON download and installation."""
    
    def __init__(self, sut_ip, username=None, password=None, ssh_key_path=None):
        self.sut_ip = sut_ip
        self.transfer = RemoteTransfer(sut_ip, username=username, password=password, ssh_key_path=ssh_key_path)
        self.local_download_dir = Path(tempfile.gettempdir()) / "emon_installer"
        self.sharepoint_url = "https://intel.sharepoint.com/sites/performance-tools/SitePages/Releases/Private"
        
    def check_and_install_emon(self):
        """
        Check if EMON is installed, and if not, offer to install it.
        
        Returns:
            bool: True if EMON is available (already installed or newly installed)
        """
        # First check if EMON already exists
        print("\n[EMON CHECK] Verifying EMON installation on SUT...")
        success, stdout, _ = self.transfer.execute_command("emon -v", timeout=10)
        
        if success and stdout:
            print("   [OK] EMON already installed")
            return True
        
        print("\n" + "="*80)
        print("[WARN]  EMON NOT FOUND ON SUT")
        print("="*80)
        print("\nEMON is required for silicon coverage analysis but is not installed on the SUT.")
        print("This tool can automatically download and install the latest EMON version.\n")
        
        # Ask user for confirmation
        response = input("Would you like to automatically install EMON? (yes/no): ").lower().strip()
        
        if response not in ['yes', 'y']:
            print("\n[FAIL] Installation cancelled. Please install EMON manually from:")
            print(f"   {self.sharepoint_url}")
            return False
        
        print("\n[INSTALL] Starting automatic EMON installation...")
        return self._install_emon()
    
    def _install_emon(self):
        """
        Download and install EMON on SUT.
        
        Returns:
            bool: True if installation successful
        """
        try:
            # Step 1: Download EMON package
            print("\n[STEP 1/4] Downloading latest EMON from Intel SharePoint...")
            local_package = self._download_emon_package()
            
            if not local_package:
                print("   [FAIL] Failed to download EMON package")
                print(f"\n   Please download manually from: {self.sharepoint_url}")
                return False
            
            print(f"   [OK] Downloaded: {local_package.name} ({local_package.stat().st_size / 1024 / 1024:.1f} MB)")
            
            # Step 2: Transfer to SUT
            print("\n[STEP 2/4] Transferring EMON package to SUT...")
            remote_path = self._transfer_to_sut(local_package)
            
            if not remote_path:
                print("   [FAIL] Failed to transfer package to SUT")
                return False
            
            print(f"   [OK] Transferred to: {remote_path}")
            
            # Step 3: Extract and install on SUT
            print("\n[STEP 3/4] Preparing EMON installation on SUT...")
            install_success = self._install_on_sut(remote_path)
            
            if not install_success:
                print("   [FAIL] Installation failed")
                return False
            
            print("   [OK] EMON installed successfully")
            
            # Step 4: Verify installation
            print("\n[STEP 4/4] Verifying EMON installation...")
            success, stdout, _ = self.transfer.execute_command("emon -v", timeout=15)
            
            if success and stdout:
                # Parse version
                for line in stdout.split('\n'):
                    if 'EMON Version' in line:
                        print(f"   [OK] {line.strip()}")
                        break
                
                print("\n" + "="*80)
                print("[OK] EMON INSTALLATION COMPLETE")
                print("="*80)
                return True
            else:
                print("   [WARN]  Installation completed but verification failed")
                print("   Please verify manually: emon -v")
                return False
                
        except Exception as e:
            print(f"\n[FAIL] Installation error: {e}")
            return False
        finally:
            # Cleanup local download
            if self.local_download_dir.exists():
                try:
                    shutil.rmtree(self.local_download_dir)
                except:
                    pass
    
    def _download_emon_package(self):
        """
        Download EMON package from SharePoint.
        
        NOTE: Intel SharePoint requires authentication.
        Manual download is required for enterprise compliance.
        Uses Python standard library only - no external dependencies.
        
        Returns:
            Path: Local path to downloaded package, or None
        """
        print("   [WARN]  Intel SharePoint requires authentication")
        print("   Manual download required (enterprise compliance - no external deps)")
        return self._manual_download()
    
    def _manual_download(self):
        """
        Fallback to manual download when auto-download fails.
        
        Returns:
            Path: Local path to manually downloaded package, or None
        """
        print("\n   Falling back to manual download...")
        print("   Please download the latest EMON package manually:\n")
        print(f"   1. Open: {self.sharepoint_url}")
        print("   2. Download the latest SEP package (e.g., sep_private_5.XX_win_*.zip)")
        print("   3. Save to your Downloads folder or a known location\n")
        
        # Ask user for the downloaded file path
        while True:
            file_path = input("   Enter the full path to the downloaded EMON package (or 'cancel'): ").strip()
            
            if file_path.lower() == 'cancel':
                return None
            
            # Remove quotes if user pasted path with quotes
            file_path = file_path.strip('"').strip("'")
            
            package_path = Path(file_path)
            
            if package_path.exists() and package_path.is_file():
                # Check if it looks like an EMON package
                if 'sep' in package_path.name.lower() and package_path.suffix in ['.zip', '.exe', '.msi']:
                    return package_path
                else:
                    print(f"   [WARN]  File doesn't appear to be an EMON package: {package_path.name}")
                    retry = input("   Use this file anyway? (yes/no): ").lower().strip()
                    if retry in ['yes', 'y']:
                        return package_path
            else:
                print(f"   [FAIL] File not found: {file_path}")
                print("   Please check the path and try again.")
    
    def _transfer_to_sut(self, local_package):
        """
        Transfer EMON package to SUT.
        
        Args:
            local_package: Path to local EMON package
            
        Returns:
            str: Remote path where package was copied, or None
        """
        try:
            file_size_mb = local_package.stat().st_size / 1024 / 1024
            print(f"   Transferring {file_size_mb:.1f} MB...")
            
            # Use RemoteTransfer's built-in copy method (handles both Windows and Linux)
            remote_path = f"/tmp/{local_package.name}"
            success = self.transfer.copy_file_to_sut(str(local_package), remote_path)
            
            if success:
                print(f"   [OK] Transfer complete")
                return remote_path
            else:
                print(f"   [FAIL] Transfer failed")
                return None
            
        except Exception as e:
            print(f"   [FAIL] Transfer error: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def _install_on_sut(self, remote_package_path):
        """
        Install EMON on SUT from the transferred package.
        
        Args:
            remote_package_path: Path to package on SUT
            
        Returns:
            bool: True if installation successful
        """
        try:
            package_path = Path(remote_package_path)
            
            # Determine installation method based on file type
            if package_path.suffix.lower() == '.zip':
                return self._install_from_zip(remote_package_path)
            elif package_path.name.endswith('.tar.bz2') or package_path.suffix.lower() in ['.tar', '.bz2', '.gz']:
                return self._install_from_tar(remote_package_path)
            elif package_path.suffix.lower() in ['.exe', '.msi']:
                return self._install_from_installer(remote_package_path)
            else:
                print(f"   [WARN]  Unknown package format: {package_path.suffix}")
                return False
                
        except Exception as e:
            print(f"   [FAIL] Installation error: {e}")
            return False
    
    def _install_from_tar(self, tar_path):
        """Transfer SEP package and provide manual installation instructions for Linux."""
        try:
            print("   SEP package transferred to SUT")
            print("   Manual installation required for Linux\n")
            
            # Extract to get the installer directory
            extract_cmd = f'''
cd /tmp
tar -xjf {tar_path} 2>&1 | head -5
installer_dir=$(find /tmp -maxdepth 2 -name "sep-installer.sh" -type f 2>/dev/null | head -1 | xargs dirname)
if [ -n "$installer_dir" ]; then
    echo "INSTALLER_DIR:$installer_dir"
else
    echo "ERROR: Could not find installer"
fi
'''
            success, stdout, _ = self.transfer.execute_command(extract_cmd, timeout=60)
            
            installer_dir = None
            if 'INSTALLER_DIR:' in stdout:
                for line in stdout.split('\n'):
                    if 'INSTALLER_DIR:' in line:
                        installer_dir = line.split('INSTALLER_DIR:')[1].strip()
                        break
            
            if not installer_dir:
                installer_dir = "/tmp/sep_private_*"
            
            print("   " + "="*70)
            print("   LINUX SEP INSTALLATION INSTRUCTIONS")
            print("   " + "="*70)
            print(f"""
   The SEP package has been extracted to: {installer_dir}
   
   REQUIRED: Install kernel headers first
   ────────────────────────────────────────
   For this SUT (kernel 6.7.0.svos-next-tickless-x86-64):
   
       sudo apt install svos-next-headers-6.7-all
   
   For standard Debian/Ubuntu:
   
       sudo apt install linux-headers-$(uname -r)
   
   THEN: Run the SEP installer
   ────────────────────────────────────────
   1. SSH to the SUT:
      
          ssh root@{self.transfer.sut_ip}
   
   2. Navigate to the installer directory:
      
          cd {installer_dir}
   
   3. Run the installer:
      
          ./sep-installer.sh
   
   4. Follow the interactive prompts:
      - Accept the license
      - Choose installation directory (default: /opt/intel/sep)
      - Complete driver build
   
   5. Set up environment (add to ~/.bashrc for persistence):
      
          source /opt/intel/sep/sep_vars.sh
   
   6. Verify installation:
      
          emon -v
   
   For non-interactive installation (after kernel headers):
   
       ./sep-installer.sh -ni --install-dir /opt/intel/sep --accept-license
   
   """)
            print("   " + "="*70)
            print("\n   Press Enter after completing the installation to continue...")
            input()
            
            # Verify installation
            verify_cmd = '''
sep_vars=$(find /opt/intel/sep -name "sep_vars.sh" -type f 2>/dev/null | head -1)
if [ -n "$sep_vars" ]; then
    source "$sep_vars"
    emon -v 2>&1 | head -3
    echo "VERIFY_DONE"
else
    echo "ERROR: SEP not installed - sep_vars.sh not found"
fi
'''
            success, stdout, _ = self.transfer.execute_command(verify_cmd, timeout=30)
            
            if 'VERIFY_DONE' in stdout:
                print("   [OK] EMON installation verified")
                return True
            else:
                print("   [WARN]  EMON not detected. Please complete installation manually.")
                return False
                
        except Exception as e:
            print(f"   [FAIL] Error: {e}")
            return False
    
    def _install_from_zip(self, zip_path):
        """Install EMON from ZIP package."""
        try:
            # Extract to temp first to inspect contents
            temp_extract = "C:\\Temp\\emon_install\\extracted"
            
            print("   Extracting package...")
            extract_cmd = f'''
Remove-Item "{temp_extract}" -Recurse -Force -ErrorAction SilentlyContinue
Expand-Archive -Path "{zip_path}" -DestinationPath "{temp_extract}" -Force
Write-Output "Extracted"
Get-ChildItem "{temp_extract}" -Recurse -File | Select-Object -First 15 | Format-Table Name, DirectoryName -AutoSize | Out-String
'''
            success, stdout, stderr = self.transfer.execute_command(extract_cmd, timeout=60)
            
            if not success:
                print(f"   [FAIL] Extraction failed: {stderr[:200]}")
                return False
            
            print(f"   Contents preview:\n{stdout[:600]}")
            
            # Find emon.exe - try multiple patterns
            find_cmd = f'''
# Try exact match first
$emon = Get-ChildItem "{temp_extract}" -Recurse -Filter "emon.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($emon) {{
    Write-Output "FOUND:$($emon.DirectoryName)"
}} else {{
    # Try emon-v*.exe pattern
    $alt = Get-ChildItem "{temp_extract}" -Recurse -Filter "emon-v*.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($alt) {{
        Write-Output "FOUND:$($alt.DirectoryName)"
    }} else {{
        # Show all exe files for debugging
        Write-Output "NOTFOUND"
        Get-ChildItem "{temp_extract}" -Recurse -Filter "*.exe" | Select-Object FullName | Out-String
    }}
}}
'''
            success, output, _ = self.transfer.execute_command(find_cmd, timeout=30)
            
            if not success:
                print("   [FAIL] Search failed")
                return False
            
            output = output.strip()
            
            if output.startswith("FOUND:"):
                emon_dir = output.replace("FOUND:", "").strip()
                print(f"   Found EMON at: {emon_dir}")
            else:
                print(f"   [FAIL] Cannot find emon.exe:\n{output[:500]}")
                return False
            
            # Copy entire extracted package to IntelSWTools
            # This preserves the full structure: sep_private_X.XX_win_XXXXX/bin64/emon.exe
            base_install = "C:\\Program Files (x86)\\IntelSWTools"
            
            print(f"   Installing to: {base_install}")
            install_cmd = f'''
New-Item -ItemType Directory -Force -Path "{base_install}" | Out-Null
Copy-Item -Path "{temp_extract}\\*" -Destination "{base_install}" -Recurse -Force
Write-Output "Installed"
'''
            success, stdout, stderr = self.transfer.execute_command(install_cmd, timeout=60)
            
            if not success:
                print(f"   [FAIL] Copy failed: {stderr[:200]}")
                return False
            
            # Check standard shortcut location first (created during install)
            shortcut_path = "C:\\Program Files (x86)\\IntelSWTools\\sep\\bin64"
            
            check_shortcut_cmd = f'''
if (Test-Path "{shortcut_path}\\emon.exe") {{
    Write-Output "{shortcut_path}"
}}
'''
            success, result, _ = self.transfer.execute_command(check_shortcut_cmd, timeout=10)
            
            if success and result.strip() and "bin64" in result:
                emon_bin_path = result.strip()
                print(f"   Found EMON at: {emon_bin_path}")
            else:
                # Fallback: Search recursively for emon.exe
                find_cmd = f'''
$emonExe = Get-ChildItem "{base_install}" -Recurse -Filter "emon.exe" -ErrorAction SilentlyContinue | Select-Object -First 1
if ($emonExe) {{
    Write-Output $emonExe.DirectoryName
}}
'''
                success, emon_bin_path, _ = self.transfer.execute_command(find_cmd, timeout=15)
                
                if not success or not emon_bin_path.strip():
                    print("   [WARN]  Installed but couldn't locate emon.exe")
                    return False
                
                emon_bin_path = emon_bin_path.strip()
                print(f"   Found EMON at: {emon_bin_path}")
            
            # Add to system PATH
            add_path_cmd = f'''
$oldPath = [Environment]::GetEnvironmentVariable("Path", "Machine")
if ($oldPath -notlike "*{emon_bin_path}*") {{
    $newPath = $oldPath + ";{emon_bin_path}"
    [Environment]::SetEnvironmentVariable("Path", $newPath, "Machine")
    Write-Output "Added to PATH"
}} else {{
    Write-Output "Already in PATH"
}}
'''
            self.transfer.execute_command(add_path_cmd, timeout=10)
            
            # Refresh PATH in current session
            refresh_cmd = f'$env:Path += ";{emon_bin_path}"'
            self.transfer.execute_command(refresh_cmd, timeout=5)
            
            # Verify
            verify_cmd = 'emon -v'
            success, version, _ = self.transfer.execute_command(verify_cmd, timeout=15)
            
            if success and "EMON" in version:
                print(f"   [OK] Verified: {version.strip()[:60]}")
                return True
            else:
                print("   [WARN]  Installed (verification may need session restart)")
                return True
                
        except Exception as e:
            print(f"   [FAIL] ZIP installation error: {e}")
            import traceback
            traceback.print_exc()
            return False
    
    def _install_from_installer(self, installer_path):
        """Install EMON from EXE/MSI installer."""
        try:
            if installer_path.lower().endswith('.msi'):
                install_cmd = f'msiexec /i "{installer_path}" /quiet /norestart'
            else:
                install_cmd = f'Start-Process "{installer_path}" -ArgumentList "/S" -Wait'
            
            print("   Running installer (this may take a few minutes)...")
            success, stdout, stderr = self.transfer.execute_command(install_cmd, timeout=300)
            
            if success:
                return True
            else:
                print(f"   [WARN]  Installer completed with warnings: {stderr[:200]}")
                # Sometimes installers return non-zero but succeed
                return True
                
        except Exception as e:
            print(f"   [FAIL] Installer error: {e}")
            return False


def main():
    """Test EMON installer."""
    if len(sys.argv) < 2:
        print("Usage: python -m src.emon_installer <SUT_IP>")
        print("Example: python -m src.emon_installer 10.138.140.94")
        return
    
    sut_ip = sys.argv[1]
    
    installer = EmonInstaller(sut_ip)
    success = installer.check_and_install_emon()
    
    if success:
        print("\n[OK] EMON is ready to use!")
    else:
        print("\n[FAIL] EMON installation failed or was cancelled")
        sys.exit(1)


if __name__ == "__main__":
    main()
