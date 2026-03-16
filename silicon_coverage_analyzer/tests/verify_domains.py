import yaml

config = yaml.safe_load(open('config/domain_config.yaml'))
print(f'Total domains: {len(config["domain_colors"])}')

new_domains = ['xyz-core', 'ddr5-mc', 'custom_cache', 'new_fabric', 'pcie_gen5']
print('\nNew domains added:')
for d in new_domains:
    if d in config['domain_colors']:
        color = config['domain_colors'][d]
        priority = config['domain_priority'][d]
        print(f'  {d}: color={color}, priority={priority}')
