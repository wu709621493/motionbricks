#!/usr/bin/env python3
"""Offline integrity, definition and accounting checks for public migration data."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / 'docs/research/china_migration'


def load_bundle(package=PACKAGE):
    data = package / 'data'
    return {
        'sources': json.loads((data / 'sources.json').read_text(encoding='utf-8')),
        'observations': [json.loads(s) for s in (data / 'observations.jsonl').read_text(encoding='utf-8').splitlines()],
        'events': [json.loads(s) for s in (data / 'historical_events.jsonl').read_text(encoding='utf-8').splitlines()],
        'geographies': json.loads((data / 'geographies.json').read_text(encoding='utf-8')),
        'panels': json.loads((data / 'genetic_reference_catalog.json').read_text(encoding='utf-8')),
        'route_cases': json.loads((data / 'us_route_cases.json').read_text(encoding='utf-8')),
    }


def require(condition, message):
    if not condition:
        raise ValueError(message)


def direct_small_cell_check(counts):
    """Explicit current AoU policy boundary, not a disclosure authorization."""
    require(all(type(n) is int and n >= 0 for n in counts), 'Counts must be nonnegative integers')
    unsafe = [i for i, n in enumerate(counts) if 1 <= n <= 20]
    return {'direct_count_threshold_pass': not unsafe,
            'unsafe_cell_indices': unsafe,
            'cross_table_disclosure_review_required': True,
            'release_authorized': False}


def validate(bundle):
    sources = {s['source_id']: s for s in bundle['sources']}
    require(len(sources) == len(bundle['sources']), 'Duplicate source ID')
    for s in sources.values():
        require(s['url'].startswith('https://'), 'Missing HTTPS source URL')
        require(s['accessed_on'] == '2026-11-15' and s['locator'] and s['limitations'], 'Incomplete source provenance')
    obs = bundle['observations']
    by_id = {o['record_id']: o for o in obs}
    require(len(by_id) == len(obs), 'Duplicate observation ID')
    required = {'record_id','series_id','year','year_basis','count','unit','measure_type','source_id',
                'source_locator','origin','destination','geography_basis','sex','data_origin','evidence_status','missing_reason'}
    for o in obs:
        require(required <= o.keys(), 'Missing observation field')
        require(o['source_id'] in sources, 'Unknown observation source')
        require(o['data_origin'] == 'public_aggregate', 'Participant or non-public data rejected')
        require(o['evidence_status'] == 'extracted' and o['missing_reason'] is None, 'Unknown counts must not be extracted observations')
        require(type(o['count']) is int and o['count'] >= 0, 'Invalid count')
        require(type(o['year']) is int and 1979 <= o['year'] <= 2026, 'Invalid observation year')
        require(o['year_basis'] in {'calendar','US_fiscal','survey_end_year'}, 'Unknown year basis')
        require(o['measure_type'] in {'stock','visa_issuance','sample_composition'}, 'Unknown measure type')
        if o['measure_type'] == 'visa_issuance':
            require(o['unit'] == 'visas' and o['year_basis'] == 'US_fiscal', 'Visa units or fiscal year confused')
        elif o['measure_type'] == 'sample_composition':
            require(o['unit'] == 'respondents' and o['year_basis'] == 'survey_end_year', 'Sample mislabelled as population')
        else:
            require(o['unit'] == 'persons', 'Stock must be persons')
        if 'male' in o:
            require(type(o['male']) is int and type(o['female']) is int and o['male'] >= 0 and o['female'] >= 0, 'Invalid sex count')
            require(o['male'] + o['female'] == o['count'], 'Sex margin mismatch')

    margins = [o for o in obs if o['series_id'] == 'nbs2020_province_margin']
    require(len(margins) == 62, 'Expected 31 origin and 31 destination margins')
    for direction in ['origin','destination']:
        rows = [o for o in margins if o['margin_direction'] == direction]
        require(len(rows) == 31 and len({o[direction] for o in rows}) == 31, 'Duplicate or missing province margin')
        require(sum(o['count'] for o in rows) == 124837153, 'Province margins fail national total')
        require(sum(o['male'] for o in rows) == 71689122, 'Male margins fail national total')
        require(sum(o['female'] for o in rows) == 53148031, 'Female margins fail national total')
    lookup = {(o['margin_direction'], o[o['margin_direction']]): o['count'] for o in margins}
    routes = [o for o in obs if o['series_id'] == 'nbs2020_selected_od']
    require(len(routes) == 56 and len({(o['origin'],o['destination']) for o in routes}) == 56, 'Selected route set changed')
    for o in routes:
        require(o['origin'] != o['destination'], 'Diagonal is outside interprovincial scope')
        require(o['geography_basis'] == 'hukou_vs_current_residence', 'Route mislabelled as birth or ancestry')
        require(o['count'] <= lookup['origin',o['origin']] and o['count'] <= lookup['destination',o['destination']], 'Route exceeds margins')
    for y in [2010,2020]:
        require(by_id[f'NBS{y}-separated']['count'] == by_id[f'NBS{y}-within_city_district']['count'] + by_id[f'NBS{y}-floating']['count'], 'Separated vs floating definitions mixed')
    require(by_id['NBS2020-floating']['count'] == by_id['NBS2020-interprovincial']['count'] + by_id['NBS2020-intraprovincial']['count'], '2020 subcounts mismatch')
    for y in [2023,2024]:
        parts = [o for o in obs if o['series_id']=='dos_iv_category' and o['year']==y]
        require(len(parts)==5 and sum(o['count'] for o in parts)==by_id[f'US-IV-{y}']['count'], 'Visa category totals mismatch')
    sample = [o for o in obs if o['series_id']=='fujian2002_2003_survey_sample']
    require(sum(o['count'] for o in sample if o['sample_category']!='total') == by_id['FJ-SURVEY-total']['count'] == 1315, 'Survey sample composition mismatch')

    gids = {g['geo_id'] for g in bundle['geographies']}
    require(len(gids) == len(bundle['geographies']), 'Duplicate geography key')
    for g in bundle['geographies']:
        require(g['historical_equivalence'] is False, 'Unsafe historical geography conversion')
        require(all(member in gids for member in g.get('members', [])), 'Unknown region member')
    for p in bundle['panels']:
        require(p['source_id'] in sources and p['individual_assignment_allowed'] is False, 'Panel cannot assign individual ancestry')
        require(all(c in gids for c in p['province_codes']), 'Unknown panel geography')
    require(len({e['event_id'] for e in bundle['events']})==len(bundle['events']), 'Duplicate event ID')
    for e in bundle['events']:
        require(e['source_id'] in sources and e['start_year'] <= e['end_year'], 'Invalid event source/dates')
        require(e['start_year'] != 0 and e['end_year'] != 0, 'Historical chronology has no year zero')
        require(e['modern_exact_count'] is None and e['genetic_linkage']=='not_tested', 'Historical quantities or genetics overstated')
    for r in bundle['route_cases']:
        require(r['source_id'] in sources and r['province_wide_count'] is None and not r['genetic_data_available'], 'Case-study scope overstated')
    return {'sources':len(sources),'observations':len(obs),'historical_events':len(bundle['events']),
            'selected_od_routes':len(routes),'province_margins':len(margins),'panel_records':len(bundle['panels'])}


def verify_manifest(package=PACKAGE, root=ROOT):
    manifest = json.loads((package/'manifest.json').read_text(encoding='utf-8'))
    for item in manifest['files']:
        path = root / item['path']
        require(path.is_relative_to(root) and '..' not in Path(item['path']).parts, 'Unsafe manifest path')
        require(hashlib.sha256(path.read_bytes()).hexdigest() == item['sha256'], 'Hash mismatch: '+item['path'])
    return len(manifest['files'])


def summary(bundle):
    obs = bundle['observations']; by_id = {o['record_id']:o for o in obs}
    f10 = by_id['NBS2010-floating']['count']; f20 = by_id['NBS2020-floating']['count']
    return {'series_record_counts':dict(sorted(Counter(o['series_id'] for o in obs).items())),
            'floating_population_growth_2010_2020_pct':(f20/f10-1)*100,
            'census_china_birth_stock_ratio_2000_to_1980':by_id['US-CENSUS-2000']['count']/by_id['US-CENSUS-1980']['count'],
            'incompatible_series_pooled':False,'aou_participants_analyzed':False,
            'interpretation':'Descriptive same-series calculations; stock changes are not gross flows or post-1979 cohort counts.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--summary',action='store_true')
    args=parser.parse_args()
    bundle=load_bundle(); result=validate(bundle); result['manifest_files_verified']=verify_manifest()
    if args.summary:result['summary']=summary(bundle)
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
