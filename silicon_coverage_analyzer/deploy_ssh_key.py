"""
One-time SSH Key Deployment Helper
Deploys SSH public key to Linux SUT for passwordless access.
"""

import subprocess
import sys
import argparse
from pathlib import Path

def deploy_key_via_password(sut_ip_override=None):
    """Deploy SSH key using password authentication."""
    print("="*80)
    print("SSH KEY DEPLOYMENT")
    print("="*80)
    print()
    
    # Load config
    import yaml
    config_path = Path(__file__).parent / "config" / "sut_config.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # Use command-line override if provided
    sut_ip = sut_ip_override
    
    if not sut_ip:
        # Try auto-detect
        print("Auto-detecting SUT IP...")
        try:
            from src.sut_communicator import SUTCommunicator
            comm = SUTCommunicator()
            sut_ip = comm.discover_sut_ip()
            print(f"[OK] Detected: {sut_ip}")
        except Exception as e:
            print(f"[FAIL] Auto-detect failed: {e}")
    else:
        print(f"[OVERRIDE] Using specified IP: {sut_ip}")
    
    # Allow manual entry if still no IP
    if not sut_ip:
        sut_ip = input("\nEnter SUT IP manually: ").strip()
        if not sut_ip:
            print("[FAIL] No SUT IP provided")
            return False
    
    print()
    username = config['sut'].get('username', 'root')
    password = config['sut'].get('password', '')
    
    if not password:
        import getpass
        password = getpass.getpass(f"Password for {username}@{sut_ip}: ")
    
    # Find SSH key
    ssh_key_path = config['sut'].get('ssh_key_path')
    if not ssh_key_path or not Path(ssh_key_path).exists():
        # Try to find generated key
        ssh_key_path = Path.home() / ".ssh" / f"silicon_analyzer_{sut_ip.replace('.', '_')}"
        if not ssh_key_path.exists():
            print(f"\n[FAIL] SSH key not found: {ssh_key_path}")
            print("   Run the analyzer first to generate the key.")
            return False
    
    pub_key_path = Path(str(ssh_key_path) + ".pub")
    if not pub_key_path.exists():
        print(f"\n[FAIL] Public key not found: {pub_key_path}")
        return False
    
    # Read public key
    with open(pub_key_path, 'r') as f:
        pub_key = f.read().strip()
    
    print(f"\nDeploying key to {username}@{sut_ip}...")
    print("This will:")
    print("  1. Create ~/.ssh directory on SUT")
    print("  2. Add public key to authorized_keys")
    print("  3. Set proper permissions")
    print()
    
    # Create deployment script
    deploy_script = f'''
mkdir -p ~/.ssh
chmod 700 ~/.ssh
echo '{pub_key}' >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
echo "SSH_KEY_DEPLOYED_OK"
'''
    
    # Try using plink if available (PuTTY)
    try:
        result = subprocess.run(['plink', '-V'], capture_output=True, timeout=2)
        print("   Using PuTTY plink for deployment...")
        
        # Use plink with password - try keyboard-interactive auth
        cmd = [
            'plink',
            '-ssh',
            '-l', username,
            '-pw', password,
            '-batch',
            sut_ip,
            deploy_script
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        
        if 'SSH_KEY_DEPLOYED_OK' in result.stdout:
            print("\n[OK] SSH key deployed successfully!")
            print("\nTesting connection...")
            
            # Test SSH key
            test_cmd = ['ssh', '-i', str(ssh_key_path), '-o', 'BatchMode=yes',
                       '-o', 'StrictHostKeyChecking=no',
                       '-o', 'ConnectTimeout=10',
                       f'{username}@{sut_ip}', 'echo "Connection test successful"']
            test_result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=10)
            
            if test_result.returncode == 0:
                print("[OK] SSH key authentication working!")
                print("\nYou can now run the analyzer without manual intervention.")
                return True
            else:
                print("[WARN]  Key deployed but test failed:", test_result.stderr)
                return False
        else:
            # plink failed, fall through to manual instructions
            if result.stderr and 'Access denied' in result.stderr:
                print("[WARN]  Password authentication failed with plink")
            elif result.stderr:
                print(f"[WARN]  plink error: {result.stderr[:200]}")
            
    except FileNotFoundError:
        print("\n[WARN]  PuTTY plink not found")
    except Exception as e:
        print(f"\n[WARN]  plink deployment failed: {e}")
    
    # Fall back to manual instructions
    print("\n" + "="*80)
    print("MANUAL SSH KEY DEPLOYMENT")
    print("="*80)
    print(f"\nYour SSH public key is ready at: {pub_key_path}")
    print(f"\nAttempting automatic deployment via SSH...")
    
    # Try to deploy using native SSH with password prompt
    deploy_cmd_oneline = f'mkdir -p ~/.ssh && chmod 700 ~/.ssh && echo \'{pub_key}\' >> ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys'
    
    print(f"\nTrying: ssh {username}@{sut_ip} ...")
    print("(You may be prompted for password)")
    
    ssh_deploy_cmd = ['ssh', '-o', 'StrictHostKeyChecking=no', 
                     '-o', 'ConnectTimeout=10',
                     f'{username}@{sut_ip}', 
                     deploy_cmd_oneline]
    
    try:
        result = subprocess.run(ssh_deploy_cmd, timeout=30)
        if result.returncode == 0:
            print("[OK] Key may have been deployed via SSH")
        else:
            print(f"[FAIL] SSH deployment returned code {result.returncode}")
    except subprocess.TimeoutExpired:
        print("[FAIL] SSH command timed out")
    except Exception as e:
        print(f"[FAIL] SSH deployment failed: {e}")
    
    print(f"\n{'─'*80}")
    print("If automatic deployment failed, deploy MANUALLY:")
    print(f"{'─'*80}")
    print(f"1. Copy this ENTIRE public key:")
    print(f"\n{pub_key}\n")
    print(f"2. SSH to your SUT:")
    print(f"   ssh {username}@{sut_ip}")
    print(f"   Password: {password if password else '(enter password)'}")
    print(f"\n3. Run these commands ONE BY ONE:")
    print(f"   mkdir -p ~/.ssh && chmod 700 ~/.ssh")
    print(f"   echo '{pub_key}' >> ~/.ssh/authorized_keys")
    print(f"   chmod 600 ~/.ssh/authorized_keys")
    
    print("\n" + "="*80)
    
    input("\n  Press Enter to test the SSH key connection...")
    
    # Test SSH key
    print("\nTesting SSH key connection...")
    test_cmd = ['ssh', '-i', str(ssh_key_path), 
               '-o', 'BatchMode=yes',
               '-o', 'StrictHostKeyChecking=no',
               '-o', 'ConnectTimeout=10',
               f'{username}@{sut_ip}', 
               'echo "SSH_KEY_TEST_OK"']
    
    try:
        test_result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=15)
        
        if test_result.returncode == 0 and 'SSH_KEY_TEST_OK' in test_result.stdout:
            print("[OK] SSH key authentication working!")
            print("\n" + "="*80)
            print("SUCCESS! You can now run:")
            print("   python analyze_coverage.py --duration 1")
            print("="*80)
            return True
        else:
            print("[FAIL] Connection test failed:")
            print(f"   Error: {test_result.stderr[:300]}")
            print("\n   The key was NOT deployed successfully.")
            print("   Please follow the MANUAL steps above and try again.")
            return False
    except Exception as e:
        print(f"[FAIL] Test error: {e}")
        return False

if __name__ == "__main__":
    # Parse command-line arguments
    parser = argparse.ArgumentParser(description='Deploy SSH key to Linux SUT')
    parser.add_argument('--sut-ip', type=str, help='SUT IP address (overrides auto-detection)')
    args = parser.parse_args()
    
    success = deploy_key_via_password(sut_ip_override=args.sut_ip)
    sys.exit(0 if success else 1)
