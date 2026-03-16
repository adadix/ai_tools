# Silicon Coverage Analyzer

**PMU Event Coverage Analysis Tool with ML-Powered Intelligence**

Version 2.0 | Intel Hardware Validation Tool

---

## 🎯 What It Does

This tool **analyzes PMU event coverage** on Intel silicon. It's designed to integrate with your existing stress/workload framework:

1. **You run** your stress tests using your automation framework
2. **This tool** collects EMON data and analyzes coverage
3. **You get** comprehensive reports with ML-powered insights

**Key Point:** This is an **analyzer**, not a stress runner. It measures coverage under whatever workload is running (or idle baseline).

---

## 🚀 Quick Start

```powershell
# 1. Install dependencies
pip install -r requirements.txt

# 2. Configure SUT (edit config/sut_config.yaml)
notepad config\sut_config.yaml

# 3. Run your stress framework (separate tool)
# ... your automation runs stress ...

# 4. Run coverage analysis
python analyze_coverage.py --duration 3

# 5. View report
start output\coverage_report.html
```

---

## 💡 Integration with Your Automation

### Typical Workflow

```python
# Your automation framework (separate)
stress_framework.start_workload("memory_stress")
time.sleep(5)  # Let workload stabilize

# Run coverage analyzer
os.system("python analyze_coverage.py --duration 10")

# Continue with your automation
stress_framework.stop_workload()
```

### What This Tool Does

✅ **Collects EMON data** from 1800+ PMU events across 9 domains  
✅ **Detects gaps** (non-toggling events)  
✅ **ML analysis** (anomalies, predictions, recommendations)  
✅ **Generates reports** (HTML dashboards, CSV exports, JSON data)  
✅ **Workload detection** (auto-detects stress tests, filters out orchestrator processes)  
✅ **Azure upload** (optional - centralized data storage)  

### What This Tool Does NOT Do

❌ **Run stress tests** (use your existing framework)  
❌ **Control workloads** (handled by your automation)  
❌ **Manage test sequences** (orchestrated by your framework)  

---

## 📖 Complete Documentation

**All documentation is now in a single file:**

### [📘 COMPLETE_REFERENCE.md](COMPLETE_REFERENCE.md)

This comprehensive guide includes:
- ✅ Installation & Setup
- ✅ Usage Guide (all collection modes)
- ✅ ML Features (local scikit-learn models)
- ✅ Understanding Reports
- ✅ Configuration Reference
- ✅ Technical Architecture
- ✅ Troubleshooting
- ✅ API Reference

---

## 💡 Key Features

- **EMON Data Collection** - Remote SUT support (Windows/Linux)
- **1800+ PMU Events** - Analyze 9 hardware domains
- **ML-Powered Analysis** - Anomaly detection, predictions, recommendations
- **Interactive Reports** - HTML dashboards with charts
- **Time-Sliced Long Runs** - Hours-long monitoring with aggregation
- **Gap Detection** - Identify untested silicon features

---

## ⚠️ Windows PowerShell Note

If the script appears to hang or pause, **press Enter** to resume. This is a PowerShell buffering issue that has been mitigated with output flushing, but may occasionally occur during long-running operations.

**Alternative:** Use Command Prompt (cmd.exe) instead of PowerShell for completely unbuffered output.

---

## 📊 Common Commands

```powershell
# Standard analysis (5-10 minutes)
python analyze_coverage.py --duration 3

# Long-run monitoring (5 hours)
python analyze_coverage.py --hours 5

# ML-powered analysis
python analyze_coverage.py --duration 3 --enable-ml

# Specific domains only
python analyze_coverage.py --domains p-core,imc --duration 3

# Train Action Prioritizer model (log which actions improved coverage)
python analyze_coverage.py --log-feedback

# Test ML features
python test_ml_integration.py
```

---

## 🤖 Training ML Models

The **Action Prioritizer** model learns from your feedback:

```powershell
# After running analysis and trying recommended actions:
python analyze_coverage.py --log-feedback

# Interactive prompt will ask:
#  - Which action did you take? (run EMON command, adjust workload, etc.)
#  - Did it improve coverage? (yes/no)
#  - How long did it take? (optional)

# After logging 5+ feedback entries, the model will train automatically
# and start ranking actions by predicted effectiveness
```

**Why log feedback?**
- Trains the Action Prioritizer to rank recommendations by success rate
- Model learns which actions work best for specific gap patterns
- Improves ML-driven prioritization in future reports

---

## 🆘 Need Help?

**Everything you need is in:** [COMPLETE_REFERENCE.md](COMPLETE_REFERENCE.md)

- Can't connect to SUT? → See "Troubleshooting" section
- Want ML features? → See "ML Features" section
- Understanding reports? → See "Understanding Reports" section
- API documentation? → See "API Reference" section

---

## 📞 Contact

**Author:** Anil Kumar Dadi  
**Email:** anil.kumar.dadi@intel.com  
**Organization:** Intel Corporation

---

**Read [COMPLETE_REFERENCE.md](COMPLETE_REFERENCE.md) for full documentation.**
