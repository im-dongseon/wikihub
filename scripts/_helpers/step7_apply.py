#!/usr/bin/env python3
"""Step 7 — 자동 적용 (archive / merge)

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
    parser = argparse.ArgumentParser(description="Step 7 — 자동 적용 (archive / merge)")
    parser.add_argument("--wiki-home", default=None,
                        help="WIKIHUB_HOME (default: $WIKIHUB_HOME > $WIKIHUB_YAML 부모 > ~/wikihub)")
    parser.add_argument("--src", default=None,
                        help="WIKIHUB_SRC (default: $WIKIHUB_SRC > ~/.local/share/wikihub/src)")
    args, _unknown = parser.parse_known_args()
    return args


_ARGS = _parse_cli()
WIKIHUB_HOME: Path = _resolve_wiki_home(_ARGS.wiki_home)
WIKIHUB_SRC: Path = _resolve_src(_ARGS.src)


import yaml
import json
import shutil
from pathlib import Path
from datetime import datetime, timezone, timedelta

KST = timezone(timedelta(hours=9))
WIKIHUB = WIKIHUB_HOME
WIKI = WIKIHUB / 'wiki'
ARCHIVED = WIKI / '.archived'
LINT = WIKI / '_lint'

def now_utc_iso():
    return datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

def read_fm(path):
    content = path.read_text(encoding='utf-8', errors='replace')
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            try:
                return yaml.safe_load(parts[1]) or {}
            except:
                return {}
    return {}

def write_fm(path, fm, body=''):
    yaml_str = yaml.dump(fm, allow_unicode=True, default_flow_style=None, sort_keys=False, line_break='\n').strip()
    content = f'---\n{yaml_str}\n---'
    if body and body.strip():
        content += '\n' + body.strip() + '\n'
    else:
        content += '\n'
    # Atomic write via tmp
    tmp = path.with_suffix('.md.tmp')
    tmp.write_text(content, encoding='utf-8')
    tmp.rename(path)

def get_body(content):
    if content.startswith('---'):
        parts = content.split('---', 2)
        if len(parts) >= 3:
            return parts[2].strip()
    return content.strip()

def archive_page(path, category):
    """Move a page to archived directory, return dest path."""
    archive_dir = ARCHIVED / category
    archive_dir.mkdir(parents=True, exist_ok=True)
    timestamp = now_utc_iso()
    archive_name = f'{path.stem}-{timestamp}.md'
    dest = archive_dir / archive_name
    # Don't archive if already archived
    count = 1
    while dest.exists():
        count += 1
        archive_name = f'{path.stem}-{timestamp}-{count}.md'
        dest = archive_dir / archive_name
    shutil.move(str(path), str(dest))
    return dest

def replace_links_in_wiki(old_link, new_link):
    """Replace [[old_link]] with [[new_link]] in all active wiki files."""
    count = 0
    files_touched = 0
    for md in WIKI.rglob('*.md'):
        rel = md.relative_to(WIKI)
        if any(part.startswith('_') or part.startswith('.') for part in rel.parts):
            continue
        content = md.read_text(encoding='utf-8', errors='replace')
        old = f'[[{old_link}]]'
        new = f'[[{new_link}]]'
        if old in content:
            content = content.replace(old, new)
            md.write_text(content, encoding='utf-8')
            count += content.count(new) - content.count(old)  # approximate
            files_touched += 1
    return {'replaced': count, 'files': files_touched}

def merge_case_variant(canonical_path, archive_path, category):
    """Merge two case-variant duplicate pages."""
    if not canonical_path.exists() or not archive_path.exists():
        return {'error': 'one or both paths missing', 'canonical': str(canonical_path), 'archive': str(archive_path)}
    
    # Read both
    fm_canon = read_fm(canonical_path)
    fm_arch = read_fm(archive_path)
    content_canon = canonical_path.read_text(encoding='utf-8', errors='replace')
    content_arch = archive_path.read_text(encoding='utf-8', errors='replace')
    
    # Merge aliases (union, dedup preserved order)
    aliases_canon = fm_canon.get('aliases', []) or []
    aliases_arch = fm_arch.get('aliases', []) or []
    if isinstance(aliases_arch, list):
        merged_aliases = list(dict.fromkeys(aliases_canon + aliases_arch))
    else:
        merged_aliases = aliases_canon
    fm_canon['aliases'] = merged_aliases
    
    # Merge referenced_by (union)
    refs_canon = fm_canon.get('referenced_by', []) or []
    refs_arch = fm_arch.get('referenced_by', []) or []
    if isinstance(refs_arch, list):
        seen = set()
        merged_refs = []
        for r in refs_canon + refs_arch:
            r_str = str(r).strip()
            if r_str not in seen:
                seen.add(r_str)
                merged_refs.append(r)
        fm_canon['referenced_by'] = merged_refs
    
    # Merge body content
    body_canon = get_body(content_canon)
    body_arch = get_body(content_arch)
    
    if not body_canon.strip() and body_arch.strip():
        final_body = body_arch
    elif body_arch.strip() and body_arch.strip()[:200] != body_canon.strip()[:200]:
        # Different content: prefer canonical, append archive note
        final_body = body_canon
        if body_arch.strip():
            final_body += '\n\n<!-- 내용 출처: ' + archive_path.stem + ' -->\n' + body_arch
    else:
        final_body = body_canon
    
    # Write canonical
    write_fm(canonical_path, fm_canon, final_body)
    
    # Archive the other
    dest = archive_page(archive_path, category)
    
    # Replace links in wiki: [[category/archive_name]] → [[category/canonical_name]]
    archive_name = archive_path.stem
    canonical_name = canonical_path.stem
    link_result = replace_links_in_wiki(f'{category}/{archive_name}', f'{category}/{canonical_name}')
    
    return {
        'canonical': str(canonical_path.relative_to(WIKIHUB)),
        'archived': str(dest.relative_to(WIKIHUB)),
        'aliases_merged': len(merged_aliases),
        'refs_merged': len(merged_refs),
        'links_replaced': link_result['replaced'],
        'files_touched': link_result['files'],
    }

def select_canonical(path_a, path_b, category):
    """Select which path is canonical (more refs, or sensible name)."""
    fm_a = read_fm(path_a)
    fm_b = read_fm(path_b)
    refs_a = len(fm_a.get('referenced_by', []) or [])
    refs_b = len(fm_b.get('referenced_by', []) or [])
    
    # Prefer the path with more references
    if refs_a > refs_b:
        return path_a, path_b
    elif refs_b > refs_a:
        return path_b, path_a
    
    # Same ref count: prefer space-separated over hyphen-separated
    name_a = path_a.stem
    name_b = path_b.stem
    a_has_space = ' ' in name_a
    b_has_space = ' ' in name_b
    if a_has_space and not b_has_space:
        return path_a, path_b
    if b_has_space and not a_has_space:
        return path_b, path_a
    
    # Same format: prefer shorter name
    if len(name_a) <= len(name_b):
        return path_a, path_b
    return path_b, path_a

def main():
    # Load duplicates
    dups_path = LINT / '_duplicates.json'
    with open(dups_path) as f:
        dups = json.load(f)
    
    case_variant = dups.get('case_variant', [])
    cross_category = dups.get('cross_category', [])
    
    applied = []
    errors = []
    skipped = []
    
    # ─── 1. Case-variant merges ───
    print('=== Step 7.1: Case-variant duplicate merges ===')
    for group in case_variant:
        pages = group.get('pages', [])
        category_dir = group.get('category_dir', 'entities')
        
        # Dedup paths
        seen_paths = set()
        unique_paths = []
        for p in pages:
            path = p['path']
            if path not in seen_paths:
                seen_paths.add(path)
                unique_paths.append(path)
        
        if len(unique_paths) < 2:
            continue
        
        # Convert to absolute paths
        abs_paths = [WIKIHUB / p for p in unique_paths]
        abs_paths = [p for p in abs_paths if p.exists()]
        
        if len(abs_paths) < 2:
            continue
        
        # Group by canonical name (pages that already share canonical should be merged together)
        # First page is the best candidate
        canonical = abs_paths[0]
        archives = abs_paths[1:]
        
        # Check if canonical is actually the one with more refs
        for p in archives:
            canonical, p = select_canonical(canonical, p, category_dir)
        
        # Rebuild list so canonical is first, rest are archives
        archives = [p for p in abs_paths if p != canonical]
        
        alias_name = group.get('alias', '')
        print(f'  Merging {len(archives)+1} pages for alias="{alias_name}": {canonical.stem} (canonical) + {[a.stem for a in archives]}')
        
        for archive_path in archives:
            if archive_path == canonical:
                continue
            if not archive_path.exists():
                continue
            
            result = merge_case_variant(canonical, archive_path, category_dir)
            if 'error' in result:
                errors.append(result)
                print(f'    ERROR: {result["error"]}')
            else:
                applied.append({**result, 'type': 'case-variant', 'alias': alias_name})
                print(f'    → archived {archive_path.stem}, merged into {canonical.stem}')
    
    # ─── 2. Cross-category merges (entity ← concept, mechanical only) ───
    print()
    print('=== Step 7.2: Cross-category duplicate merges ===')
    already_merged_entities = set()
    
    for group in cross_category:
        pages = group.get('pages', [])
        
        # Separate entity and concept paths
        entity_paths = []
        concept_paths = []
        for p in pages:
            path_str = p['path']
            if 'entities/' in path_str:
                entity_paths.append(path_str)
            elif 'concepts/' in path_str:
                concept_paths.append(path_str)
        
        if not entity_paths:
            skipped.append({'reason': 'no entity path', 'alias': group.get('alias')})
            continue
        if not concept_paths:
            skipped.append({'reason': 'no concept path', 'alias': group.get('alias')})
            continue
        
        # Use first entity as canonical
        # (if multiple entities, merge them first as case-variant)
        entity_canonical_str = entity_paths[0]
        # Pick entity with most refs
        entity_fm_list = [(p, read_fm(WIKIHUB / p)) for p in entity_paths]
        entity_fm_list.sort(key=lambda x: len(x[1].get('referenced_by', []) or []), reverse=True)
        entity_canonical_str = entity_fm_list[0][0]
        
        entity_path = WIKIHUB / entity_canonical_str
        if not entity_path.exists():
            skipped.append({'reason': 'entity path missing', 'path': entity_canonical_str})
            continue
        
        fm_ent = read_fm(entity_path)
        
        # Skip if already merged (merged_from marker present)
        if fm_ent.get('merged_from'):
            already_merged_entities.add(entity_canonical_str)
            continue
        
        alias_name = group.get('alias', '')
        
        for concept_str in concept_paths:
            concept_path = WIKIHUB / concept_str
            if not concept_path.exists():
                continue
            
            fm_con = read_fm(concept_path)
            
            # Merge referenced_by (union)
            refs_ent = fm_ent.get('referenced_by', []) or []
            refs_con = fm_con.get('referenced_by', []) or []
            if isinstance(refs_con, list):
                seen = set(str(r).strip() for r in (refs_ent or []))
                merged_refs = list(refs_ent or [])
                for r in refs_con:
                    r_str = str(r).strip()
                    if r_str not in seen:
                        seen.add(r_str)
                        merged_refs.append(r)
                fm_ent['referenced_by'] = merged_refs
            
            # Merge aliases (union)
            aliases_ent = fm_ent.get('aliases', []) or []
            aliases_con = fm_con.get('aliases', []) or []
            if isinstance(aliases_con, list):
                merged_aliases = list(dict.fromkeys(aliases_ent + aliases_con))
                fm_ent['aliases'] = merged_aliases
            
            # Add merged_from marker
            merged_from = fm_ent.get('merged_from', []) or []
            concept_slug = concept_path.stem
            if concept_slug not in merged_from:
                merged_from.append(concept_slug)
            fm_ent['merged_from'] = merged_from
            
            # Include concept body if entity body is empty
            ent_content = entity_path.read_text(encoding='utf-8', errors='replace')
            ent_body = get_body(ent_content)
            con_body = get_body(concept_path.read_text(encoding='utf-8', errors='replace'))
            
            if not ent_body.strip() and con_body.strip():
                ent_body = con_body
            
            # Write entity
            write_fm(entity_path, fm_ent, ent_body)
            
            # Archive concept
            dest = archive_page(concept_path, 'concepts')
            
            applied.append({
                'type': 'cross-category',
                'alias': alias_name,
                'canonical': str(entity_path.relative_to(WIKIHUB)),
                'archived': str(dest.relative_to(WIKIHUB)),
                'merged_refs': len(refs_con) if isinstance(refs_con, list) else 0,
            })
            print(f'  Merged concept "{concept_path.stem}" → entity "{entity_path.stem}" (alias="{alias_name}")')
    
    # ─── Summary ───
    print()
    print(f'=== Step 7 Summary ===')
    print(f'  Total merges applied: {len(applied)}')
    print(f'  - Case-variant: {sum(1 for a in applied if a.get("type") == "case-variant")}')
    print(f'  - Cross-category: {sum(1 for a in applied if a.get("type") == "cross-category")}')
    print(f'  Errors: {len(errors)}')
    print(f'  Skipped (already merged): {len(already_merged_entities)}')
    print(f'  Skipped (other): {len(skipped)}')
    
    # Save results
    result = {
        'timestamp': now_utc_iso(),
        'applied': applied,
        'errors': errors,
        'skipped': skipped,
        'count': len(applied),
    }
    out_path = LINT / '_fixes_applied.json'
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'  Results saved to {out_path}')

if __name__ == '__main__':
    main()
