#!/usr/bin/env python3
"""
Windows SUT Setup Helper

Configures TrustedHosts and verifies WinRM connectivity for Windows SUTs.
Run this once per Windows SUT to enable PowerShell remoting.

Usage:
    python setup_windows_sut.py [--sut-ip IP] [--username USER] [--password PASS]
"""

import subprocess
import yaml
import argparse
from pathlib import Path

def parse_args():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Configure Windows SUT for PowerShell remoting')
    parser.add_argument('--sut-ip', help='SUT IP address')
    parser.add_argument('--username', help='Username for authentication')
    parser.add_argument('--password', help='Password for authentication')
    return parser.parse_args()

def load_sut_config():
    """Load SUT configuration."""
    config_path = Path("config/sut_config.yaml")
    if not config_path.exists():
        return {}
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)

def check_winrm_service():
    """Check if WinRM service is running on local machine."""
    print("\n[1/4] Checking WinRM service status...")
    try:
        result = subprocess.run(
            ['powershell', '-Command', 'Get-Service WinRM | Select-Object -ExpandProperty Status'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and 'Running' in result.stdout:
            print("   [OK] WinRM service is running")
            return True
        else:
            print("   [WARN]  WinRM service is not running")
            print("   Run: Start-Service WinRM")
            return False
    except Exception as e:
        print(f"   [FAIL] Error checking WinRM: {e}")
        return False

def get_current_trusted_hosts():
    """Get current TrustedHosts configuration."""
    try:
        result = subprocess.run(
            ['powershell', '-Command', 'Get-Item WSMan:\\localhost\\Client\\TrustedHosts | Select-Object -ExpandProperty Value'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            return result.stdout.strip()
        return ""
    except:
        return ""

def add_to_trusted_hosts(sut_ip):
    """Add SUT IP to TrustedHosts."""
    print(f"\n[2/4] Configuring TrustedHosts for {sut_ip}...")
    
    current = get_current_trusted_hosts()
    
    if current:
        print(f"   Current TrustedHosts: {current}")
        
        # Check if already in list
        if sut_ip in current.split(','):
            print(f"   [OK] {sut_ip} already in TrustedHosts")
            return True
        
        # Add to existing list
        new_value = f"{current},{sut_ip}"
    else:
        new_value = sut_ip
    
    try:
        # Set TrustedHosts
        cmd = f'Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value "{new_value}" -Force'
        result = subprocess.run(
            ['powershell', '-Command', cmd],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            print(f"   [OK] Added {sut_ip} to TrustedHosts")
            return True
        else:
            print(f"   [FAIL] Failed to add to TrustedHosts: {result.stderr}")
            print(f"\n   Manual command:")
            print(f"   Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value \"{new_value}\" -Force")
            return False
    except Exception as e:
        print(f"   [FAIL] Error: {e}")
        return False

def test_winrm_connection(sut_ip, username, password):
    """Test WinRM connection to SUT."""
    print(f"\n[3/4] Testing WinRM connection to {sut_ip}...")
    
    try:
        # Create credential and test basic command
        script = f'''
$pass = ConvertTo-SecureString "{password}" -AsPlainText -Force
$cred = New-Object System.Management.Automation.PSCredential("{username}", $pass)
Invoke-Command -ComputerName {sut_ip} -Credential $cred -ScriptBlock {{ $env:COMPUTERNAME }} -ErrorAction Stop
'''
        
        result = subprocess.run(
            ['powershell', '-Command', script],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0 and result.stdout.strip():
            computer_name = result.stdout.strip()
            print(f"   [OK] Connection successful! SUT hostname: {computer_name}")
            return True
        else:
            print(f"   [FAIL] Connection failed")
            if result.stderr:
                print(f"   Error: {result.stderr[:200]}")
            return False
    except subprocess.TimeoutExpired:
        print(f"   [FAIL] Connection timeout - check if SUT is reachable")
        return False
    except Exception as e:
        print(f"   [FAIL] Error: {e}")
        return False

def check_winrm_on_sut(sut_ip):
    """Check if WinRM is accessible on SUT."""
    print(f"\n[4/4] Checking WinRM service on SUT ({sut_ip})...")
    
    try:
        result = subprocess.run(
            ['powershell', '-Command', f'Test-NetConnection -ComputerName {sut_ip} -Port 5985 -WarningAction SilentlyContinue | Select-Object -ExpandProperty TcpTestSucceeded'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0 and 'True' in result.stdout:
            print(f"   [OK] WinRM port 5985 is accessible on SUT")
            return True
        else:
            print(f"   [FAIL] WinRM port 5985 is NOT accessible on SUT")
            print(f"\n   On the SUT, run:")
            print(f"   Enable-PSRemoting -Force")
            print(f"   Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value \"*\" -Force")
            return False
    except Exception as e:
        print(f"   [WARN]  Could not check SUT WinRM status: {e}")
        return False

def main():
    print("="*70)
    print("Windows SUT Setup - PowerShell Remoting Configuration")
    print("="*70)
    
    # Parse command line arguments
    args = parse_args()
    
    # Load config file
    config = load_sut_config()
    
    # Use command-line args or fall back to config file
    sut_ip = args.sut_ip or config.get('sut_ip', '')
    username = args.username or config.get('username', 'Administrator')
    password = args.password or config.get('password', '')
    
    if not sut_ip:
        print("\n[FAIL] No SUT IP specified!")
        print("\nUsage:")
        print("  python setup_windows_sut.py --sut-ip 10.138.140.94")
        print("  python setup_windows_sut.py --sut-ip 10.138.140.94 --username admin --password pass123")
        print("\nOr configure in config/sut_config.yaml")
        return
    
    print(f"\nTarget SUT: {sut_ip}")
    print(f"Username: {username}")
    
    # Step 1: Check local WinRM
    if not check_winrm_service():
        print("\n[WARN]  Start WinRM service first:")
        print("   Start-Service WinRM")
        return
    
    # Step 2: Configure TrustedHosts
    if not add_to_trusted_hosts(sut_ip):
        print("\n[WARN]  TrustedHosts configuration failed")
        print("   You may need to run this script as Administrator")
        return
    
    # Step 3: Check SUT WinRM availability
    check_winrm_on_sut(sut_ip)
    
    # Step 4: Test connection
    if username and password:
        test_winrm_connection(sut_ip, username, password)
    else:
        print("\n[WARN]  No credentials configured - skipping connection test")
    
    print("\n" + "="*70)
    print("Setup Complete!")
    print("="*70)
    print("\nYou can now run: python analyze_coverage.py")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nSetup cancelled by user")
    except Exception as e:
        print(f"\n[FAIL] Unexpected error: {e}")
