# Domain Configuration Quick Reference

## File Location
`config/domain_config.yaml`

## Quick Edits

### Change Domain Color
```yaml
domain_colors:
  p-core: '#0071C5'  # Change this hex code
```

### Change Domain Priority (1=Low, 2=Medium, 3=High)
```yaml
domain_priority:
  p-core: 3  # High priority - analyzed first
  e-core: 2  # Medium priority
```

### Add New Stress Tool
```yaml
stress_tool_domains:
  my_new_test:
    domains: [p-core, imc]          # Which domains it stresses
    categories: [cpu_cores, memory_subsystem]  # Categories
    type: mixed                     # compute|memory|mixed|baseline
    intensity: high                 # low|medium|high|extreme
```

### Modify ML Domain Lists
```yaml
ml_domain_lists:
  workload_detector:
    - p-core
    - e-core
    - imc
    # Add more domains here
```

### Add Architecture Profile
```yaml
architectures:
  my_platform:
    name: "My Platform Name"
    products: [ProductA, ProductB]
    domains: [p-core, e-core, imc, cbo, ncu]
```

## Domain Categories

| Category | Purpose | Example Domains |
|----------|---------|----------------|
| `cpu_cores` | Processor execution cores | p-core, e-core, atom |
| `memory_subsystem` | Memory controllers | imc, hbm, m2m |
| `cache_coherency` | Cache management | cbo, cha, llc |
| `interconnect` | Inter-core communication | ncu, upi, mesh |
| `io_subsystem` | I/O interfaces | iio, pcie, ufibridge |
| `power_management` | Power/frequency | power |
| `uncore_general` | General uncore | uncore, offcore |

## Stress Tool Types

- **compute**: CPU-intensive (prime95, linpack)
- **memory**: Memory-intensive (memtester, stream)
- **mixed**: CPU+Memory (stress-ng, sandstone)
- **baseline**: Idle/minimal activity

## Intensity Levels

- **low**: Minimal stress (idle, light workloads)
- **medium**: Moderate stress (stream, sysbench)
- **high**: Heavy stress (prime95, memtester)
- **extreme**: Maximum stress (linpack, y-cruncher)

## Common Customizations

### 1. Add Custom Intel Tool
```yaml
stress_tool_domains:
  my_validation_tool:
    domains: [p-core, e-core, imc, cbo]
    categories: [cpu_cores, memory_subsystem, cache_coherency]
    type: mixed
    intensity: high
```

### 2. Change Domain Display Order
Modify `domain_priority` - higher numbers = analyzed first:
```yaml
domain_priority:
  critical_domain: 3  # First
  important_domain: 2  # Second
  optional_domain: 1  # Last
```

### 3. Highlight Specific Domains in Reports
Add to `critical_domains`:
```yaml
critical_domains:
  - p-core
  - e-core
  - my_custom_domain  # Add here
```

### 4. Customize Domain Colors for Branding
```yaml
domain_colors:
  p-core: '#YOUR_COLOR'
  e-core: '#YOUR_COLOR'
  # Use hex codes or CSS color names
```

## Validation

Test your changes:
```powershell
python test_domain_config.py
```

Should output:
```
✅ Domain config loaded successfully!
   - X domain colors
   - Y domain priorities
   - Z categories
```

## Common Issues

### Config Not Loading
- Check YAML syntax (no tabs, proper indentation)
- Verify file location: `config/domain_config.yaml`
- Run: `python test_domain_config.py`

### Missing Domain
- Add to `domain_colors` AND `domain_priority`
- Add to appropriate `domain_categories`
- Restart analysis

### Stress Tool Not Recognized
- Add to `stress_tool_domains` section
- Ensure domains exist in `domain_colors`
- Check `config/stress_tools.yaml` also configured

## Architecture Selection (Future)

Currently Intel-only. Structure supports future multi-vendor:
```yaml
architectures:
  client_hybrid:
    products: [AlderLake, RaptorLake, MeteorLake]
    domains: [p-core, e-core, imc, cbo, ncu]
  
  server_sapphire:
    products: [SapphireRapids]
    domains: [core, cha, imc, upi, m2m]
```

## Recommendations Section

Customize messages:
```yaml
recommendations:
  cpu_cores_idle:
    condition: "p-core or e-core domains show low stress"
    message: "Your custom recommendation here"
```

## Need Help?

See `DOMAIN_CONFIG_REFACTORING.md` for full documentation.
