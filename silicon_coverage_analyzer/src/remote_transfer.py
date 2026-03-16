"""
Remote Transfer Module for SUT Communication

INTEL CONFIDENTIAL - INTERNAL USE ONLY

This module handles file transfer and remote execution between host and SUT.
Supports both Windows and Linux targets with automatic protocol detection.
Uses only standard library - no external dependencies (subprocess-based SSH/SCP).

Author: Intel Corporation
Date: November 2025
"""

import os
import subprocess
import logging
import tempfile
import shutil
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import time
import json
import socket

logger = logging.getLogger(__name__)


class RemoteTransfer:
    """
    Handles remote file transfer and command execution on SUT.
    Supports SSH (Linux) and PowerShell remoting (Windows).
    """
    
    def __init__(self, sut_ip: str, username: str = None, password: str = None, ssh_key_path: str = None, collection_hours: float = None):
        """
        Initialize remote transfer client.
        
        Args:
            sut_ip: SUT IP address
            username: Username for authentication
            password: Password for authentication
            ssh_key_path: Path to SSH private key (for Linux SUTs)
            collection_hours: Expected collection duration in hours (adds 1 hour buffer for WinRM timeout)
        """
        self.sut_ip = sut_ip
        self.username = username or self._get_default_username()
        self.password = password
        self.ssh_key_path = ssh_key_path
        self.connection_type = None  # 'ssh', 'winrm', or 'psremoting'
        self.temp_dir = tempfile.mkdtemp(prefix="silicon_analyzer_")
        
        # Keepalive configuration to prevent connection timeouts during long collections
        self.ssh_keepalive_interval = 30  # Send keepalive every 30 seconds
        self.ssh_keepalive_count_max = 120  # Allow 120 missed keepalives (60 minutes)
        self.winrm_keepalive_minutes = 120  # WinRM idle timeout: 2 hours
        self.itp_session = None  # Will hold ITP session if available
        self.sut_os_type = None  # 'windows' or 'linux'
        
        # Calculate WinRM timeout: (collection_hours + 1 hour buffer) in milliseconds
        # Default to 12 hours if not specified
        self.winrm_timeout_ms = int((collection_hours + 1) * 3600000) if collection_hours else 43200000
        
        logger.info(f"Initializing remote transfer to {sut_ip}")
        if collection_hours:
            logger.info(f"WinRM timeout set to {collection_hours + 1:.1f} hours ({self.winrm_timeout_ms}ms)")
        self._check_itp_session()
        self._detect_connection_type()
        
        # Configure WinRM if needed (only if not using ITP)
        if self.connection_type == 'psremoting' and not self.itp_session:
            self._setup_winrm_access()
    
    def _get_default_username(self) -> str:
        """Get default username based on current user."""
        return 'administrator'
    
    def _get_ps_session_options(self) -> str:
        """
        Generate PowerShell session options string with timeout configuration.
        Centralized method to avoid duplication across 5 locations.
        
        Returns:
            str: PowerShell New-PSSessionOption command with timeout settings
        """
        return f"New-PSSessionOption -SkipCACheck -SkipCNCheck -SkipRevocationCheck -OperationTimeout {self.winrm_timeout_ms} -IdleTimeout {self.winrm_timeout_ms}"
    
    def _check_itp_session(self):
        """Check if there's an active ITP session we can use."""
        try:
            import sys
            # Check if running in ITP environment
            if hasattr(sys.modules.get('__main__', {}), 'itp'):
                itp = getattr(sys.modules['__main__'], 'itp')
                if hasattr(itp, 'communicator'):
                    # Check if this is the same SUT that ITP is connected to
                    try:
                        target_ip = getattr(itp.communicator, 'target_ip', None)
                        if target_ip == self.sut_ip:
                            self.itp_session = itp
                            logger.info(f"Using ITP session for {self.sut_ip}")
                            return
                    except:
                        pass
        except Exception as e:
            logger.debug(f"ITP session check failed: {e}")
        
        self.itp_session = None
    
    def _detect_connection_type(self):
        """Detect the best connection method for the SUT."""
        # Test SSH (port 22) - Linux/Unix systems
        if self._test_port(22):
            self.connection_type = 'ssh'
            self.sut_os_type = 'linux'
            logger.info("Detected SSH connectivity (Linux/Unix SUT)")
            return
        
        # Test PowerShell remoting (port 5985/5986) - Windows systems
        if self._test_port(5985) or self._test_port(5986):
            self.connection_type = 'psremoting'
            self.sut_os_type = 'windows'
            logger.info("Detected PowerShell remoting (Windows SUT)")
            return
        
        # Test RDP (port 3389) as fallback - Windows systems
        if self._test_port(3389):
            self.connection_type = 'psremoting'
            self.sut_os_type = 'windows'
            logger.info("Detected RDP port, assuming Windows with WinRM (run setup_windows_sut.py if needed)")
            return
        
        logger.warning(f"Could not detect any open ports on {self.sut_ip} (tried SSH/WinRM/RDP)")
        logger.warning("Defaulting to SSH - this will likely fail")
        self.connection_type = 'ssh'
        self.sut_os_type = 'linux'
    
    def _setup_winrm_access(self):
        """Configure WinRM access for the target SUT."""
        try:
            logger.info(f"Configuring WinRM access for {self.sut_ip}")
            
            # Check if SUT is already in TrustedHosts
            check_cmd = ['powershell.exe', '-Command', 
                        f'(Get-Item WSMan:\\localhost\\Client\\TrustedHosts -ErrorAction SilentlyContinue).Value']
            result = subprocess.run(check_cmd, capture_output=True, text=True, timeout=30)
            
            current_hosts = result.stdout.strip()
            
            # Check if already configured
            if self.sut_ip in current_hosts or '*' in current_hosts:
                logger.info(f"SUT {self.sut_ip} already in TrustedHosts")
                return
            
            # Add to TrustedHosts - use elevated powershell automatically
            logger.info(f"Adding {self.sut_ip} to WinRM TrustedHosts (may prompt for admin)...")
            
            if current_hosts:
                new_hosts = f"{current_hosts},{self.sut_ip}"
            else:
                new_hosts = self.sut_ip
            
            # Create a script to run with elevation
            script_content = f'''
# Configure WinRM TrustedHosts
try {{
    $currentHosts = (Get-Item WSMan:\\localhost\\Client\\TrustedHosts -ErrorAction SilentlyContinue).Value
    if ($currentHosts -notlike "*{self.sut_ip}*" -and $currentHosts -ne "*") {{
        Set-Item WSMan:\\localhost\\Client\\TrustedHosts -Value "{new_hosts}" -Force
        Write-Output "SUCCESS: Added {self.sut_ip} to TrustedHosts"
    }} else {{
        Write-Output "ALREADY_CONFIGURED"
    }}
}} catch {{
    Write-Error "FAILED: $($_.Exception.Message)"
    exit 1
}}
'''
            
            script_path = os.path.join(self.temp_dir, "setup_winrm.ps1")
            with open(script_path, 'w', encoding='utf-8') as f:
                f.write(script_content)
            
            # Run with elevation using Start-Process -Verb RunAs
            setup_cmd = ['powershell.exe', '-Command', 
                        f'Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File \\"{script_path}\\"" -Verb RunAs -Wait -WindowStyle Hidden']
            
            result = subprocess.run(setup_cmd, capture_output=True, text=True, timeout=30)
            
            # Clean up
            try:
                os.remove(script_path)
            except:
                pass
            
            if result.returncode == 0 or "SUCCESS" in result.stdout or "ALREADY_CONFIGURED" in result.stdout:
                logger.info(f"WinRM configured successfully for {self.sut_ip}")
            else:
                logger.warning(f"WinRM setup may have failed, will attempt connection anyway")
                
        except Exception as e:
            logger.warning(f"Could not configure WinRM automatically: {e}")
            logger.info("Attempting connection without TrustedHosts configuration...")
    
    def _test_port(self, port: int, timeout: int = 10) -> bool:
        """Test if a port is open on the SUT."""
        import socket
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout)
            result = sock.connect_ex((self.sut_ip, port))
            sock.close()
            return result == 0
        except Exception:
            return False
    
    def copy_file_to_sut(self, local_path: str, remote_path: str) -> bool:
        """
        Copy a file from host to SUT.
        
        Args:
            local_path: Local file path
            remote_path: Remote destination path
            
        Returns:
            bool: True if successful
        """
        try:
            if self.connection_type == 'ssh':
                return self._scp_to_sut(local_path, remote_path)
            elif self.connection_type == 'psremoting':
                return self._ps_copy_to_sut(local_path, remote_path)
            else:
                logger.error(f"Unsupported connection type: {self.connection_type}")
                return False
        except Exception as e:
            logger.error(f"Failed to copy file to SUT: {e}")
            return False
    
    def copy_file_from_sut(self, remote_path: str, local_path: str) -> bool:
        """
        Copy a file from SUT to host with retry logic and validation.
        
        Args:
            remote_path: Remote file path
            local_path: Local destination path
            
        Returns:
            bool: True if successful
        """
        # Try up to 3 times with increasing delays
        for attempt in range(3):
            try:
                # First verify file exists on SUT (OS-specific commands)
                if self.connection_type == 'ssh':
                    verify_cmd = f'[ -f "{remote_path}" ] && echo "true" || echo "false"'
                else:
                    verify_cmd = f'Test-Path "{remote_path}"'
                success, output, _ = self.execute_command(verify_cmd, timeout=30)
                
                if not success or output.strip().lower() != 'true':
                    logger.warning(f"File {remote_path} not found on SUT (attempt {attempt+1}/3)")
                    if attempt < 2:
                        time.sleep(1 * (attempt + 1))
                        continue
                    return False
                
                # Get file size to verify it has content (OS-specific commands)
                if self.connection_type == 'ssh':
                    size_cmd = f'stat -f%z "{remote_path}" 2>/dev/null || stat -c%s "{remote_path}" 2>/dev/null'
                else:
                    size_cmd = f'(Get-Item "{remote_path}").Length'
                success, size_output, _ = self.execute_command(size_cmd, timeout=30)
                
                if success and size_output.strip():
                    try:
                        file_size = int(size_output.strip())
                        if file_size == 0:
                            logger.warning(f"File {remote_path} is empty (attempt {attempt+1}/3)")
                            if attempt < 2:
                                time.sleep(1 * (attempt + 1))
                                continue
                            return False
                    except ValueError:
                        pass
                
                # Attempt file transfer
                if self.connection_type == 'ssh':
                    result = self._scp_from_sut(remote_path, local_path)
                elif self.connection_type == 'psremoting':
                    result = self._ps_copy_from_sut(remote_path, local_path)
                else:
                    logger.error(f"Unsupported connection type: {self.connection_type}")
                    return False
                
                # Verify local file was created and has content
                if result and os.path.exists(local_path) and os.path.getsize(local_path) > 0:
                    logger.info(f"Successfully copied {remote_path} from SUT (attempt {attempt+1})")
                    return True
                else:
                    logger.warning(f"Transfer appeared successful but file validation failed (attempt {attempt+1}/3)")
                    if attempt < 2:
                        time.sleep(1 * (attempt + 1))
                        continue
                
            except Exception as e:
                logger.error(f"Failed to copy file from SUT (attempt {attempt+1}/3): {e}")
                if attempt < 2:
                    time.sleep(1 * (attempt + 1))
                    continue
        
        logger.error(f"Failed to copy {remote_path} from SUT after 3 attempts")
        return False
    
    def copy_from_sut(self, remote_path: str, local_path: str) -> bool:
        """Alias for copy_file_from_sut for backward compatibility."""
        return self.copy_file_from_sut(remote_path, local_path)
    
    def execute_command(self, command: str, timeout: int = 300) -> Tuple[bool, str, str]:
        """
        Execute a command on the SUT.
        
        Args:
            command: Command to execute
            timeout: Timeout in seconds
            
        Returns:
            Tuple[bool, str, str]: (success, stdout, stderr)
        """
        try:
            # If we have an ITP session, use it for command execution
            if self.itp_session:
                return self._itp_execute(command, timeout)
            
            if self.connection_type == 'ssh':
                return self._ssh_execute(command, timeout)
            elif self.connection_type == 'psremoting':
                return self._ps_execute(command, timeout)
            else:
                logger.error(f"Unsupported connection type: {self.connection_type}")
                return False, "", "Unsupported connection type"
        except Exception as e:
            logger.error(f"Failed to execute command on SUT: {e}")
            return False, "", str(e)
    
    def _itp_execute(self, command: str, timeout: int) -> Tuple[bool, str, str]:
        """Execute command using ITP session."""
        try:
            # Use ITP's PowerShell execution capability
            result = self.itp_session.communicator.run_powershell(command)
            if result:
                return True, str(result), ""
            else:
                return False, "", "No output from ITP command"
        except Exception as e:
            logger.error(f"ITP command execution failed: {e}")
            # Fall back to PowerShell remoting
            return self._ps_execute(command, timeout)
    
    def _scp_to_sut(self, local_path: str, remote_path: str) -> bool:
        """Copy file using native SCP command (standard library only)."""
        # Check if scp/ssh is available
        if not self._check_ssh_available():
            logger.error("SSH/SCP commands not available on this system")
            return False
        
        # Try plink/pscp for password authentication
        if self.password:
            pscp_cmd = [
                'pscp',
                '-batch',
                '-pw', self.password,
                local_path,
                f"{self.username}@{self.sut_ip}:{remote_path}"
            ]
            
            try:
                result = subprocess.run(pscp_cmd, capture_output=True, text=True, timeout=60)
                if result.returncode == 0:
                    logger.info(f"Successfully copied {local_path} to SUT using pscp")
                    return True
            except FileNotFoundError:
                logger.debug("pscp not available, trying standard scp")
            except subprocess.TimeoutExpired:
                logger.debug("SCP operation timed out")
                return False
        
        # Fall back to standard SCP (requires key-based auth)
        cmd = [
            'scp',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            '-o', 'ConnectTimeout=10',
            '-o', 'BatchMode=yes',
            '-o', 'ServerAliveInterval=60',
            '-o', 'ServerAliveCountMax=10',
            '-o', 'TCPKeepAlive=yes',
        ]
        
        # Add SSH key if specified
        if self.ssh_key_path and os.path.exists(self.ssh_key_path):
            cmd.extend(['-i', self.ssh_key_path])
            logger.debug(f"Using SSH key: {self.ssh_key_path}")
        
        cmd.extend([
            local_path,
            f"{self.username}@{self.sut_ip}:{remote_path}"
        ])
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                logger.info(f"Successfully copied {local_path} to SUT")
                return True
            else:
                logger.error(f"SCP failed: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            logger.debug("SCP operation timed out")
            return False
        except Exception as e:
            logger.error(f"SCP error: {e}")
            return False
    
    def _scp_from_sut(self, remote_path: str, local_path: str) -> bool:
        """Copy file from SUT using native SCP command (standard library only)."""
        # Check if scp/ssh is available
        if not self._check_ssh_available():
            logger.error("SSH/SCP commands not available on this system")
            return False
        
        # Try pscp for password authentication
        if self.password:
            pscp_cmd = [
                'pscp',
                '-batch',
                '-pw', self.password,
                f"{self.username}@{self.sut_ip}:{remote_path}",
                local_path
            ]
            
            try:
                result = subprocess.run(pscp_cmd, capture_output=True, text=True, timeout=300)
                if result.returncode == 0:
                    logger.info(f"Successfully copied {remote_path} from SUT using pscp")
                    return True
            except FileNotFoundError:
                logger.debug("pscp not available, trying standard scp")
            except subprocess.TimeoutExpired:
                logger.debug("SCP operation timed out after 300 seconds")
                return False
        
        # Fall back to standard SCP (requires key-based auth)
        cmd = [
            'scp',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            '-o', 'ConnectTimeout=10',
            '-o', 'BatchMode=yes',
            '-o', 'ServerAliveInterval=60',
            '-o', 'ServerAliveCountMax=10',
            '-o', 'TCPKeepAlive=yes',
        ]
        
        # Add SSH key if specified
        if self.ssh_key_path and os.path.exists(self.ssh_key_path):
            cmd.extend(['-i', self.ssh_key_path])
            logger.debug(f"Using SSH key: {self.ssh_key_path}")
        
        cmd.extend([
            f"{self.username}@{self.sut_ip}:{remote_path}",
            local_path
        ])
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            if result.returncode == 0:
                logger.info(f"Successfully copied {remote_path} from SUT")
                return True
            else:
                logger.error(f"SCP failed: {result.stderr}")
                return False
        except subprocess.TimeoutExpired:
            logger.debug(f"SCP operation timed out after 300 seconds")
            return False
        except Exception as e:
            logger.error(f"SCP error: {e}")
            return False
    
    def _ssh_execute(self, command: str, timeout: int) -> Tuple[bool, str, str]:
        """Execute command via native SSH (standard library only)."""
        # Check if ssh is available
        if not self._check_ssh_available():
            logger.error("SSH command not available on this system")
            return False, "", "SSH not available"
        
        # Build SSH command with keep-alive and key file if available
        cmd = [
            'ssh',
            '-o', 'StrictHostKeyChecking=no',
            '-o', 'UserKnownHostsFile=/dev/null',
            '-o', 'ConnectTimeout=10',
            '-o', 'BatchMode=yes',  # Disable interactive password prompts
            '-o', f'ServerAliveInterval={self.ssh_keepalive_interval}',  # Send keep-alive every 30s
            '-o', f'ServerAliveCountMax={self.ssh_keepalive_count_max}',  # Retry 120 times (60 minutes)
            '-o', 'TCPKeepAlive=yes',  # Enable TCP keep-alive
        ]
        
        # Add SSH key if specified
        if self.ssh_key_path and os.path.exists(self.ssh_key_path):
            cmd.extend(['-i', self.ssh_key_path])
            logger.debug(f"Using SSH key: {self.ssh_key_path}")
        
        cmd.extend([f"{self.username}@{self.sut_ip}", command])
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            success = result.returncode == 0
            return success, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            logger.debug(f"SSH command timed out after {timeout} seconds")
            return False, "", "Command timed out"
        except Exception as e:
            logger.error(f"SSH execution error: {e}")
            return False, "", str(e)
    
    def _check_ssh_available(self) -> bool:
        """Check if SSH/SCP commands are available on the system."""
        try:
            # Try to find ssh command
            result = subprocess.run(['ssh', '-V'], capture_output=True, text=True, timeout=15)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    
    def _ps_copy_to_sut(self, local_path: str, remote_path: str) -> bool:
        """Copy file using PowerShell remoting."""
        # Create PowerShell script for copying - handle empty password case
        ps_script = f"""
        try {{
            $sessionOption = {self._get_ps_session_options()}
            $session = New-PSSession -ComputerName {self.sut_ip} -SessionOption $sessionOption -ErrorAction Stop
            Copy-Item -Path "{local_path}" -Destination "{remote_path}" -ToSession $session -Force -ErrorAction Stop
            Remove-PSSession $session
            Write-Output "SUCCESS"
        }} catch {{
            Write-Error $_.Exception.Message
            exit 1
        }}
        """
        
        script_path = os.path.join(self.temp_dir, "copy_to_sut.ps1")
        with open(script_path, 'w') as f:
            f.write(ps_script)
        
        cmd = ['powershell.exe', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', script_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and 'SUCCESS' in result.stdout:
            logger.info(f"Successfully copied {local_path} to SUT via PowerShell")
            return True
        else:
            logger.error(f"PowerShell copy failed: {result.stderr}")
            return False
    
    def _ps_copy_from_sut(self, remote_path: str, local_path: str) -> bool:
        """Copy file from SUT using PowerShell remoting."""
        ps_script = f"""
        try {{
            $sessionOption = {self._get_ps_session_options()}
            $session = New-PSSession -ComputerName {self.sut_ip} -SessionOption $sessionOption -ErrorAction Stop
            Copy-Item -Path "{remote_path}" -Destination "{local_path}" -FromSession $session -Force -ErrorAction Stop
            Remove-PSSession $session
            Write-Output "SUCCESS"
        }} catch {{
            try {{
                # Fallback with Administrator credentials
                $password = New-Object System.Security.SecureString
                $credential = New-Object System.Management.Automation.PSCredential ("Administrator", $password)
                $sessionOption = {self._get_ps_session_options()}
                $session = New-PSSession -ComputerName {self.sut_ip} -Credential $credential -Authentication Negotiate -SessionOption $sessionOption -ErrorAction Stop
                Copy-Item -Path "{remote_path}" -Destination "{local_path}" -FromSession $session -Force -ErrorAction Stop
                Remove-PSSession $session
                Write-Output "SUCCESS"
            }} catch {{
                Write-Error $_.Exception.Message
                exit 1
            }}
        }}
        """
        
        script_path = os.path.join(self.temp_dir, "copy_from_sut.ps1")
        with open(script_path, 'w') as f:
            f.write(ps_script)
        
        cmd = ['powershell.exe', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', script_path]
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0 and 'SUCCESS' in result.stdout:
            logger.info(f"Successfully copied {remote_path} from SUT via PowerShell")
            return True
        else:
            logger.error(f"PowerShell copy failed: {result.stderr}")
            return False
    
    def _ps_execute(self, command: str, timeout: int) -> Tuple[bool, str, str]:
        """Execute command via PowerShell remoting."""
        # For IP addresses, explicit credentials are required
        # Handle truly empty password by using Read-Host with empty input
        
        if not self.password or self.password == '':
            # Empty password - use SecureString with no characters
            ps_script = f"""
$ErrorActionPreference = 'Stop'

try {{
    # For empty password, use Get-Credential with preset empty password
    $password = New-Object System.Security.SecureString
    # Password is empty - just create empty SecureString
    $credential = New-Object System.Management.Automation.PSCredential ("{self.username}", $password)
    
    # Set OperationTimeout and IdleTimeout dynamically based on collection hours
    $so = {self._get_ps_session_options()}
    $result = Invoke-Command -ComputerName {self.sut_ip} -Credential $credential -SessionOption $so -Authentication Negotiate -ScriptBlock {{
        {command}
    }} -ErrorAction Stop 2>&1
    if ($result) {{
        $result | Out-String
    }}
    exit 0
}} catch {{
    Write-Error "Connection failed: $($_.Exception.Message)"
    exit 1
}}
"""
        else:
            # Non-empty password
            ps_script = f"""
$ErrorActionPreference = 'Stop'

try {{
    $securePassword = ConvertTo-SecureString "{self.password}" -AsPlainText -Force
    $credential = New-Object System.Management.Automation.PSCredential ("{self.username}", $securePassword)
    
    # Set OperationTimeout and IdleTimeout dynamically based on collection hours
    $so = {self._get_ps_session_options()}
    $result = Invoke-Command -ComputerName {self.sut_ip} -Credential $credential -SessionOption $so -Authentication Negotiate -ScriptBlock {{
        {command}
    }} -ErrorAction Stop 2>&1
    if ($result) {{
        $result | Out-String
    }}
    exit 0
}} catch {{
    Write-Error "Connection failed: $($_.Exception.Message)"
    exit 1
}}
"""
        
        script_path = os.path.join(self.temp_dir, f"exec_{int(time.time()*1000)}.ps1")
        with open(script_path, 'w', encoding='utf-8') as f:
            f.write(ps_script)
        
        try:
            cmd = ['powershell.exe', '-NonInteractive', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', script_path]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            
            # Clean up script file
            try:
                os.remove(script_path)
            except:
                pass
            
            success = result.returncode == 0
            return success, result.stdout, result.stderr
        except subprocess.TimeoutExpired:
            logger.debug(f"PowerShell command timed out after {timeout} seconds")
            try:
                os.remove(script_path)
            except:
                pass
            return False, "", "Command timed out"
        except Exception as e:
            logger.error(f"PowerShell execution failed: {e}")
            return False, "", str(e)
    
    def test_connection(self) -> bool:
        """
        Test connection to SUT using autonomous authentication.
        
        Returns:
            bool: True if connection successful
        """
        try:
            # Use the autonomous authenticator's test methods
            if self.connection_type == 'ssh':
                return self.autonomous_auth.test_ssh_connection()
            
            elif self.connection_type in ['psremoting', 'winrm']:
                return self.autonomous_auth.test_powershell_connection()
            
            # Fallback - try both methods
            return (self.autonomous_auth.test_powershell_connection() or 
                   self.autonomous_auth.test_ssh_connection())
            
        except Exception as e:
            logger.error(f"Autonomous connection test failed: {e}")
            return False
    
    def cleanup(self):
        """Clean up temporary files and close connections."""
        try:
            # Remove temporary directory
            shutil.rmtree(self.temp_dir)
            logger.info("Cleaned up temporary files")
        except Exception as e:
            logger.warning(f"Failed to clean up: {e}")
    
    def get_sut_system_info(self) -> Dict[str, Any]:
        """Get basic system information from SUT."""
        info = {
            'ip_address': self.sut_ip,
            'connection_type': self.connection_type,
            'username': self.username,
            'os_type': 'unknown',
            'hostname': 'unknown',
            'arch': 'unknown'
        }
        
        # Try to get OS information
        if self.connection_type == 'ssh':
            # Linux/Unix commands
            commands = {
                'hostname': 'hostname',
                'os_type': 'uname -s',
                'arch': 'uname -m'
            }
        else:
            # Windows commands
            commands = {
                'hostname': '$env:COMPUTERNAME',
                'os_type': '(Get-WmiObject Win32_OperatingSystem).Caption',
                'arch': '$env:PROCESSOR_ARCHITECTURE'
            }
        
        for key, cmd in commands.items():
            try:
                success, stdout, _ = self.execute_command(cmd, timeout=60)
                if success:
                    info[key] = stdout.strip()
            except Exception as e:
                logger.warning(f"Failed to get {key}: {e}")
        
        return info


if __name__ == "__main__":
    # Test remote transfer
    logging.basicConfig(level=logging.INFO)
    
    # This would use actual SUT IP from discovery
    test_ip = "192.168.1.100"
    transfer = RemoteTransfer(test_ip)
    
    if transfer.test_connection():
        print("Remote transfer connection successful")
        info = transfer.get_sut_system_info()
        print(f"SUT Info: {info}")
    else:
        print("Remote transfer connection failed")
    
    transfer.cleanup()