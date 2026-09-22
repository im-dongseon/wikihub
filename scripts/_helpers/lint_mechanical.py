#!/usr/bin/env python3
"""wh-lint 기계적 검증 (Step 1 / 1.5 / 2 / 4.5)

WikiHub 정본 helper (#201 ⑥ 정본화, ADR-0034 data-first layout 정합).

경로 복원 체계 (fail-safe 순서):
  1. `--wiki-home` / `--src` CLI arg
  2. `WIKIHUB_HOME` / `WIKIHUB_SRC` env
  3. `WIKIHUB_YAML` env 의 부모 디렉토리  (lint/graphify/ingest systemd unit 이 주입)
  4. `~/wikihub` / `~/.local/share/wikihub/src`  (ADR-0034 default)

원 운영 로컬 버전(`$WIKIHUB_HOME/_scripts/`)은 `/home/ubuntu/wikihub` 을
하드코딩했으나, 본 정본은 이식 가능하게 정규화했다. **판정 로직은 무변경.**
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _resolve_wiki_home(explicit: "str | None" = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("WIKIHUB_HOME")
    if env:
        return Path(env).expanduser().resolve()
    yaml_env = os.environ.get("WIKIHUB_YAML")
    if yaml_env:
        return Path(yaml_env).expanduser().resolve().parent
    return Path("~/wikihub").expanduser().resolve()


def _resolve_src(explicit: "str | None" = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    env = os.environ.get("WIKIHUB_SRC")
    if env:
        return Path(env).expanduser().resolve()
    return Path("~/.local/share/wikihub/src").expanduser().resolve()


def _parse_cli() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="wh-lint 기계적 검증 (Step 1 / 1.5 / 2 / 4.5)")
    parser.add_argument("--wiki-home", default=None,
                        help="WIKIHUB_HOME (default: $WIKIHUB_HOME > $WIKIHUB_YAML 부모 > ~/wikihub)")
    parser.add_argument("--src", default=None,
                        help="WIKIHUB_SRC (default: $WIKIHUB_SRC > ~/.local/share/wikihub/src)")
    args, _unknown = parser.parse_known_args()
    return args


_ARGS = _parse_cli()
WIKIHUB_HOME: Path = _resolve_wiki_home(_ARGS.wiki_home)
WIKIHUB_SRC: Path = _resolve_src(_ARGS.src)



import json
import os
import sys
import subprocess
import re
import yaml
from pathlib import Path
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))

WIKIHUB_HOME = WIKIHUB_HOME
WIKI_ROOT = WIKIHUB_HOME / 'wiki'
LINT_DIR = WIKI_ROOT / '_lint'
SRC_DIR = WIKIHUB_SRC

def now_kst():
    return datetime.now(KST).strftime('%Y-%m-%d %H:%M KST')

def report(*, dirs_ok=None, alias_index=None, link_violations=None, duplicates=None):
    """Collect and return all step results."""
    result = {
        'timestamp': now_kst(),
        'steps': {}
    }
    if dirs_ok is not None:
        result['steps']['step1_dirs'] = dirs_ok
    if alias_index is not None:
        result['steps']['step15_alias_index'] = {
            'count': len(alias_index),
        }
    if link_violations is not None:
        result['steps']['step2_link_violations'] = link_violations
    if duplicates is not None:
        result['steps']['step45_duplicates'] = duplicates
    return result


# ─── Step 1: 디렉토리 검증 ───

def step1_dirs():
    result = {
        'created': [],
        'missing': [],
        'wiki_root_files': [],
        'vaults': [],
    }

    required_categories = ['sources', 'entities', 'concepts', 'analyses', '_lint']

    # Vault 목록: wikihub.yaml 에서 enabled vaults
    yaml_path = WIKIHUB_HOME / 'wikihub.yaml'
    if yaml_path.exists():
        with open(yaml_path) as f:
            config = yaml.safe_load(f)
        vault_ids = [v['id'] for v in config.get('vaults', []) if v.get('enabled', True)]
    else:
        vault_ids = []
    result['vaults'] = vault_ids

    # 4 categories + _lint
    for cat in required_categories:
        p = WIKI_ROOT / cat
        if not p.exists():
            p.mkdir(parents=True)
            result['created'].append(str(p.relative_to(WIKIHUB_HOME)))

    # vault별 sources/{vault}/
    for vid in vault_ids:
        p = WIKI_ROOT / 'sources' / vid
        if not p.exists():
            p.mkdir(parents=True)
            result['created'].append(str(p.relative_to(WIKIHUB_HOME)))

    # wiki/ 직속 파일 중 index.md 외
    for f in WIKI_ROOT.iterdir():
        if f.is_file() and f.suffix == '.md' and f.name != 'index.md':
            result['wiki_root_files'].append(str(f.relative_to(WIKIHUB_HOME)))

    # .archived/
    archived = WIKI_ROOT / '.archived'
    if not archived.exists():
        archived.mkdir()
        result['created'].append('.archived/')
    for sub in ['entities', 'concepts', 'sources']:
        p = archived / sub
        if not p.exists():
            p.mkdir()
            result['created'].append(str(p.relative_to(WIKIHUB_HOME)))

    return result


# ─── Step 1.5: Alias index build ───

def read_frontmatter(path):
    """Try to read YAML frontmatter from a markdown file."""
    content = path.read_text(encoding='utf-8', errors='replace')
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                fm = yaml.safe_load(parts[1])
                return fm if isinstance(fm, dict) else {}
            except yaml.YAMLError:
                return {}
    return {}


def step15_alias_index():
    alias_index = {}
    conflicts = []
    for category in ('entities', 'concepts'):
        cat_dir = WIKI_ROOT / category
        if not cat_dir.exists():
            continue
        for page in sorted(cat_dir.glob('*.md')):
            canonical = page.stem
            fm = read_frontmatter(page)
            aliases = fm.get('aliases')
            if not aliases or not isinstance(aliases, list):
                aliases = [canonical]
            for alias in aliases:
                if not isinstance(alias, str):
                    continue
                key = alias.strip().lower()
                if not key:
                    continue
                if key in alias_index and alias_index[key] != canonical:
                    conflicts.append({
                        'alias': key,
                        'existing_canonical': alias_index[key],
                        'new_canonical': canonical,
                        'category': category,
                    })
                    continue
                alias_index[key] = canonical
    return alias_index, conflicts


# ─── Step 2: ADR-0001 link 규약 검증 ───

def extract_links(content):
    """Extract all [[links]] from markdown content."""
    return re.findall(r'\[\[([^\]]+)\]\]', content)


def step2_links(alias_index, vault_ids):
    violations = {
        'no_prefix_sources': [],      # 위반 1: sources link without vault prefix
        'unknown_vault_prefix': [],    # 위반 2: [[unknown/path]] with unknown vault
        'dangling_full_path': [],      # 위반 3: [[vault/path]] where file missing
        'dangling_short_entity': [],   # [[name]] entity/concept not found via alias
        'dangling_short_concept': [],  # [[name]] entity/concept not found via alias
    }

    # Build set of all page stems for quick lookup
    entity_pages = {p.stem for p in (WIKI_ROOT / 'entities').glob('*.md')}
    concept_pages = {p.stem for p in (WIKI_ROOT / 'concepts').glob('*.md')}

    # Step 2 resolver: check [[name]] via alias or exact match
    def resolve_short_link(name, category_stems, category_dir_name):
        """Check if [[name]] resolves to an existing page in category."""
        name_clean = name.strip()
        # Exact match
        for stem in category_stems:
            if stem.lower() == name_clean.lower():
                return True
        # Alias match
        key = name_clean.lower()
        if key in alias_index:
            return True
        # Direct file check
        p = WIKI_ROOT / category_dir_name / f'{name_clean}.md'
        if p.exists():
            return True
        return False

    # 모든 wiki 페이지 스캔
    all_md_files = list(WIKI_ROOT.rglob('*.md'))
    # Skip _lint/ and .archived/
    all_md_files = [f for f in all_md_files
                    if not any(part.startswith('_') or part.startswith('.') for part in f.relative_to(WIKI_ROOT).parts)]

    for md_path in all_md_files:
        rel_path = str(md_path.relative_to(WIKIHUB_HOME))
        content = md_path.read_text(encoding='utf-8', errors='replace')
        links = extract_links(content)

        for link in links:
            link = link.strip()
            if '/' in link:
                # Full path: [[category/path]] or [[vault/path]]
                prefix = link.split('/')[0]

                # 위반 2: unknown vault prefix
                if prefix not in vault_ids and prefix not in ('entities', 'concepts', 'analyses', 'sources'):
                    violations['unknown_vault_prefix'].append({
                        'link': link,
                        'source': rel_path,
                    })
                    continue

                # 위반 1: sources category link without vault prefix? No, sources links should be [[sources/vault/path]]
                # Actually, the rule says source page links without vault prefix
                # [[report]] - short form pointing to source without prefix
                # But we already know it has a /, so it's not short form
                # Check for source vault prefix validity
                if prefix in vault_ids:
                    # 위반 3: vault prefix exists but path doesn't
                    if prefix == 'gdrive':
                        # gdrive is historical - might not be active
                        pass
                    # source path: wiki/sources/<vault>/<rest>.md
                    link_path_parts = link.split('/')
                    expected_source_path = WIKI_ROOT / 'sources' / link_path_parts[0] / '/'.join(link_path_parts[1:])
                    # wiki 저장 관례는 <원본파일명>.<ext>.md (예: x.pdf -> x.pdf.md, x.py -> x.py.md).
                    # Path('a/b/c.pdf').with_suffix('.md') 는 원 확장자를 잘라버려 (c.md) 틀림.
                    # 링크가 .md 로 끝나면 그대로, 아니면 .md 를 뒤에 추가해 확인.
                    expected_source_file = expected_source_path if expected_source_path.suffix == '.md' else Path(str(expected_source_path) + '.md')
                    if not expected_source_file.exists():
                        violations['dangling_full_path'].append({
                            'link': link,
                            'source': rel_path,
                            'expected': str(expected_source_file.relative_to(WIKIHUB_HOME)),
                        })
            else:
                # 단축형 [[name]]
                # Check entities first, then concepts
                found_entity = resolve_short_link(link, entity_pages, 'entities')
                found_concept = resolve_short_link(link, concept_pages, 'concepts')

                if not found_entity and not found_concept:
                    violations['dangling_short_entity'].append({
                        'link': link,
                        'source': rel_path,
                    })

    return violations


# ─── Step 4.5: Duplicate detection ───

def step45_duplicates():
    helper = SRC_DIR / 'scripts' / '_helpers' / 'detect_alias_duplicates.py'
    if not helper.exists():
        return {'error': f'detect_alias_duplicates.py not found at {helper}'}

    try:
        result = subprocess.run(
            ['python3', str(helper), '--wiki-home', str(WIKIHUB_HOME)],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode != 0:
            return {'error': f'exit code {result.returncode}', 'stderr': result.stderr}
        return json.loads(result.stdout)
    except Exception as e:
        return {'error': str(e)}

    # ─── Alias migration (Step 4.5 보조) ───
def step45_alias_migration():
    """Add aliases: [<canonical>] to pages missing aliases frontmatter."""
    modified = []
    skipped = []
    for category in ('entities', 'concepts'):
        cat_dir = WIKI_ROOT / category
        if not cat_dir.exists():
            continue
        for page in sorted(cat_dir.glob('*.md')):
            content = page.read_text(encoding='utf-8', errors='replace')
            canonical = page.stem
            fm = read_frontmatter(page)
            if not fm:
                skipped.append(str(page.relative_to(WIKIHUB_HOME)))
                continue
            aliases = fm.get('aliases')
            if aliases is None or (isinstance(aliases, list) and len(aliases) == 0):
                # Need to add aliases
                if content.startswith('---'):
                    parts = content.split('---', 2)
                    if len(parts) == 3:
                        new_fm = yaml.safe_load(parts[1])
                        new_fm['aliases'] = [canonical]
                        new_yaml = yaml.dump(new_fm, allow_unicode=True, default_flow_style=None, sort_keys=False).strip()
                        new_content = f'---\n{new_yaml}\n---{parts[2]}'
                        # Atomic write
                        tmp = page.with_suffix('.md.tmp')
                        tmp.write_text(new_content, encoding='utf-8')
                        tmp.rename(page)
                        modified.append(str(page.relative_to(WIKIHUB_HOME)))
    return {'modified': modified, 'skipped': skipped}


# ─── MAIN ───

def main():
    result = {}

    # Step 1
    dirs = step1_dirs()
    result['step1'] = dirs

    # Step 1.5
    alias_index, conflicts = step15_alias_index()
    result['step15'] = {
        'alias_count': len(alias_index),
        'alias_conflicts': conflicts,
    }

    # Save alias_index for later steps
    alias_index_path = LINT_DIR / '_alias_index.json'
    alias_index_path.parent.mkdir(parents=True, exist_ok=True)
    alias_index_path.write_text(json.dumps(alias_index, ensure_ascii=False, indent=2), encoding='utf-8')

    # Step 2
    vault_ids = dirs['vaults']
    violations = step2_links(alias_index, vault_ids)
    result['step2'] = violations

    # Save link violations
    violations_path = LINT_DIR / '_link_violations.json'
    violations_path.write_text(json.dumps(violations, ensure_ascii=False, indent=2), encoding='utf-8')

    # Step 4.5 duplicate detection
    duplicates = step45_duplicates()
    result['step45_duplicates'] = duplicates

    # Step 4.5 alias migration
    alias_migration = step45_alias_migration()
    result['step45_alias_migration'] = alias_migration

    # Save duplicates
    dups_path = LINT_DIR / '_duplicates.json'
    dups_path.write_text(json.dumps(duplicates, ensure_ascii=False, indent=2), encoding='utf-8')

    # Write to stdout for consumption
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # Summary to stderr
    n_violations = (len(violations.get('no_prefix_sources', [])) +
                    len(violations.get('unknown_vault_prefix', [])) +
                    len(violations.get('dangling_full_path', [])) +
                    len(violations.get('dangling_short_entity', [])) +
                    len(violations.get('dangling_short_concept', [])))
    n_dups = len(duplicates.get('case_variant', [])) + len(duplicates.get('cross_category', []))
    print(f'[lint] Step 1: {len(dirs["created"])} dirs created', file=sys.stderr)
    print(f'[lint] Step 1.5: {len(alias_index)} aliases indexed, {len(conflicts)} conflicts', file=sys.stderr)
    print(f'[lint] Step 2: {n_violations} link violations', file=sys.stderr)
    print(f'[lint] Step 4.5: {n_dups} duplicate groups, {len(alias_migration["modified"])} pages aliases added', file=sys.stderr)

if __name__ == '__main__':
    main()
