#!/usr/bin/env python3
"""Step 7 — alias / referenced_by 보정 적용

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
    parser = argparse.ArgumentParser(description="Step 7 — alias / referenced_by 보정 적용")
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
from pathlib import Path
from datetime import datetime, timezone, timedelta
import shutil
import sys

KST = timezone(timedelta(hours=9))
WIKIHUB = WIKIHUB_HOME
WIKI = WIKIHUB / 'wiki'
ARCHIVED = WIKI / '.archived'

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
    if body:
        content += '\n' + body.strip() + '\n'
    else:
        content += '\n'
    path.write_text(content, encoding='utf-8')

def replace_in_wiki(old_link, new_link):
    """Replace [[old_link]] with [[new_link]] in all wiki files."""
    count = 0
    for md in WIKI.rglob('*.md'):
        if any(part.startswith('_') or part.startswith('.') for part in md.relative_to(WIKI).parts):
            continue
        content = md.read_text(encoding='utf-8', errors='replace')
        old = f'[[{old_link}]]'
        new = f'[[{new_link}]]'
        if old in content:
            content = content.replace(old, new)
            md.write_text(content, encoding='utf-8')
            count += 1
    return count

def merge_pages(canonical_path, archive_path, category):
    """Merge two duplicate pages. canonical_path wins."""
    if not canonical_path.exists() or not archive_path.exists():
        return {'error': 'one path missing', 'canonical': str(canonical_path), 'archive': str(archive_path)}

    fm_canon = read_fm(canonical_path)
    fm_arch = read_fm(archive_path)
    body_canon = canonical_path.read_text(encoding='utf-8', errors='replace')
    body_arch = archive_path.read_text(encoding='utf-8', errors='replace')
    
    # Extract body (after frontmatter)
    def get_body(content):
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 3:
                return parts[2].strip()
        return content.strip()
    
    canon_body = get_body(body_canon)
    arch_body = get_body(body_arch)
    
    # Merge aliases (union)
    aliases_canon = fm_canon.get('aliases', []) or []
    aliases_arch = fm_arch.get('aliases', []) or []
    merged_aliases = list(dict.fromkeys(aliases_canon + aliases_arch))  # order-preserving dedup
    
    # Merge referenced_by (union)
    refs_canon = fm_canon.get('referenced_by', []) or []
    refs_arch = fm_arch.get('referenced_by', []) or []
    # Remove duplicates while preserving order
    seen = set()
    merged_refs = []
    for r in refs_canon + refs_arch:
        r_str = str(r)
        if r_str not in seen:
            seen.add(r_str)
            merged_refs.append(r)
    
    # Update canonical page
    fm_canon['aliases'] = merged_aliases
    fm_canon['referenced_by'] = merged_refs
    
    # Merge body: use canonical body, append archive body if substantially different
    # Simple heuristic: if archive body has meaningful content not in canonical
    arch_words = set(arch_body.lower().split())
    canon_words = set(canon_body.lower().split())
    new_words = arch_words - canon_words
    if len(new_words) > 3 and len(arch_body) > 50:
        if canon_body:
            fm_canon['description'] = (fm_canon.get('description', '') or '') or (fm_arch.get('description', '') or '')
            # Keep canonical body, note archive content
        else:
            canon_body = arch_body
    
    # Write canonical
    write_fm(canonical_path, fm_canon, canon_body)
    
    # Archive the other
    archive_subdir = ARCHIVED / category
    archive_subdir.mkdir(parents=True, exist_ok=True)
    timestamp = now_utc_iso()
    archive_name = f'{archive_path.stem}-{timestamp}.md'
    archive_dest = archive_subdir / archive_name
    
    # Move (not copy) to archive
    shutil.move(str(archive_path), str(archive_dest))
    
    return {
        'canonical': str(canonical_path.relative_to(WIKIHUB)),
        'archived': str(archive_dest.relative_to(WIKIHUB)),
        'merged_aliases': len(merged_aliases),
        'merged_refs': len(merged_refs),
        'new_words_from_archive': len(new_words),
    }

def main():
    applied = []
    errors = []
    
    # ─── Case-variant duplicates ───
    case_variant_pairs = [
        ('entities/Blink Shell.md', 'entities/Blink-Shell.md'),
        ('entities/John Lee.md', 'entities/John-Lee.md'),
        ('entities/John MacFarlane.md', 'entities/John-MacFarlane.md'),
        ('entities/Kiro CLI.md', 'entities/Kiro-CLI.md'),
        ('concepts/Adaptive-Scheduler.md', 'concepts/적응형-스케줄러.md'),
        ('concepts/Agent Registry.md', 'concepts/Agent-Registry-Pattern.md'),
        ('concepts/Guardrails.md', 'concepts/가드레일 (Guardrails).md'),
        ('concepts/Long-term-Memory.md', 'concepts/기억 저장소.md'),
        ('concepts/Structured state.md', 'concepts/Structured-state.md'),
        ('concepts/Tool Factory.md', 'concepts/Tool-Factory-Pattern.md'),
        ('concepts/Transcript 접근법.md', 'concepts/Transcript-접근법.md'),
        ('concepts/토큰 효율성.md', 'concepts/토큰-효율성.md'),
    ]
    
    for p1, p2 in case_variant_pairs:
        fp1 = WIKI / p1
        fp2 = WIKI / p2
        
        if not fp1.exists() or not fp2.exists():
            continue
        
        # Determine canonical: first form (with spaces) typically has more refs
        fm1 = read_fm(fp1)
        fm2 = read_fm(fp2)
        refs1 = len(fm1.get('referenced_by', []))
        refs2 = len(fm2.get('referenced_by', []))
        
        # Pick the one with more references as canonical
        if refs1 >= refs2:
            canonical_path = fp1
            archive_path = fp2
            canonical_name = fp1.stem
            archive_name = fp2.stem
        else:
            canonical_path = fp2
            archive_path = fp1
            canonical_name = fp2.stem
            archive_name = fp1.stem
        
        category = 'entities' if 'entities' in p1 else 'concepts'
        
        result = merge_pages(canonical_path, archive_path, category)
        result['pair'] = [p1, p2]
        result['canonical_name'] = canonical_name
        result['archive_name'] = archive_name
        
        # Replace [[archive_name]] → [[canonical_name]] in wiki
        link_old = f'{category}/{archive_name}'
        link_new = f'{category}/{canonical_name}'
        replaced = replace_in_wiki(link_old, link_new)
        result['links_replaced'] = replaced
        
        applied.append(result)
        print(f'[merge] {archive_name} → {canonical_name} (archived, {replaced} links replaced)')
    
    # ─── Cross-category duplicates (already merged: OPAL-루프, 에이전틱-AI) ───
    # These have merged_from already - just archive concept page + merge refs
    already_merged = [
        ('entities/OPAL-루프.md', 'concepts/OPAL 루프.md'),
        ('entities/에이전틱-AI.md', 'concepts/에이전틱 AI.md'),
    ]
    
    for ent_path_str, con_path_str in already_merged:
        ent_path = WIKI / ent_path_str
        con_path = WIKI / con_path_str
        
        if not ent_path.exists() or not con_path.exists():
            continue
        
        fm_ent = read_fm(ent_path)
        fm_con = read_fm(con_path)
        
        # Merge referenced_by
        refs_ent = fm_ent.get('referenced_by', []) or []
        refs_con = fm_con.get('referenced_by', []) or []
        seen = set()
        merged_refs = []
        for r in refs_ent + refs_con:
            r_str = str(r)
            if r_str not in seen:
                seen.add(r_str)
                merged_refs.append(r)
        fm_ent['referenced_by'] = merged_refs
        
        # Merge aliases
        aliases_ent = fm_ent.get('aliases', []) or []
        aliases_con = fm_con.get('aliases', []) or []
        merged_aliases = list(dict.fromkeys(aliases_ent + aliases_con))
        fm_ent['aliases'] = merged_aliases
        
        # Keep existing merged_from marker
        write_fm(ent_path, fm_ent)
        
        # Archive concept
        archive_subdir = ARCHIVED / 'concepts'
        archive_subdir.mkdir(parents=True, exist_ok=True)
        timestamp = now_utc_iso()
        archive_name = f'{con_path.stem}-{timestamp}.md'
        archive_dest = archive_subdir / archive_name
        shutil.move(str(con_path), str(archive_dest))
        
        applied.append({
            'type': 'cross-category-already-merged',
            'entity': str(ent_path.relative_to(WIKIHUB)),
            'archived': str(archive_dest.relative_to(WIKIHUB)),
            'action': 'archive concept, merge refs/aliases',
        })
        print(f'[merge] cross-category: archived {con_path.stem}, merged refs into {ent_path.stem}')
    
    # ─── Cross-category duplicates needing LLM merge ───
    # These are more complex - need LLM to merge concept body into entity body
    cross_category_pending = [
        ('entities/Agent-Service-Toolkit.md', 'concepts/에이전트 서비스 툴킷.md'),
        ('entities/CF Access.md', 'concepts/CF Access.md'),
        ('entities/DateTimeOriginal.md', 'concepts/DateTimeOriginal.md'),
        ('entities/DeepSeek.md', 'concepts/DeepSeek.md'),
        ('entities/Hyper Backup.md', 'concepts/Hyper Backup.md'),
        ('entities/Jina-AI.md', 'concepts/Jina-Reader.md'),
        ('entities/MCP.md', 'concepts/MCP.md'),
        ('entities/PostgreSQL.md', 'concepts/PostgreSQL.md'),
        ('entities/TokenJuice.md', 'concepts/TokenJuice.md'),
    ]
    
    # For now: do mechanical merge (merge refs + aliases, archive concept, skip LLM body merge)
    # Mark with merged_from so future lint can skip LLM
    for ent_path_str, con_path_str in cross_category_pending:
        ent_path = WIKI / ent_path_str
        con_path = WIKI / con_path_str
        
        if not ent_path.exists() or not con_path.exists():
            continue
        
        fm_ent = read_fm(ent_path)
        fm_con = read_fm(con_path)
        
        # Check if already merged
        if fm_ent.get('merged_from'):
            continue
        
        # Merge referenced_by (union)
        refs_ent = fm_ent.get('referenced_by', []) or []
        refs_con = fm_con.get('referenced_by', []) or []
        seen = set()
        merged_refs = []
        for r in refs_ent + refs_con:
            r_str = str(r)
            if r_str not in seen:
                seen.add(r_str)
                merged_refs.append(r)
        fm_ent['referenced_by'] = merged_refs
        
        # Merge aliases (union)
        aliases_ent = fm_ent.get('aliases', []) or []
        aliases_con = fm_con.get('aliases', []) or []
        merged_aliases = list(dict.fromkeys(aliases_ent + aliases_con))
        fm_ent['aliases'] = merged_aliases
        
        # Mark merged_from for idempotency
        merged_from = fm_ent.get('merged_from', [])
        merged_from.append(con_path_str.replace('concepts/', ''))
        fm_ent['merged_from'] = merged_from
        
        # Get concept body for reference
        con_body = ''
        con_content = con_path.read_text(encoding='utf-8', errors='replace')
        if con_content.startswith('---'):
            parts = con_content.split('---', 2)
            if len(parts) >= 3:
                con_body = parts[2].strip()
        
        # Append concept body to entity body if entity has no body
        ent_content = ent_path.read_text(encoding='utf-8', errors='replace')
        ent_body = ''
        if ent_content.startswith('---'):
            parts = ent_content.split('---', 2)
            if len(parts) >= 3:
                ent_body = parts[2].strip()
        
        if not ent_body.strip() and con_body.strip():
            ent_body = con_body
        
        # Write entity
        write_fm(ent_path, fm_ent, ent_body)
        
        # Archive concept
        archive_subdir = ARCHIVED / 'concepts'
        archive_subdir.mkdir(parents=True, exist_ok=True)
        timestamp = now_utc_iso()
        archive_name = f'{con_path.stem}-{timestamp}.md'
        archive_dest = archive_subdir / archive_name
        shutil.move(str(con_path), str(archive_dest))
        
        applied.append({
            'type': 'cross-category-merge',
            'entity': str(ent_path.relative_to(WIKIHUB)),
            'archived': str(archive_dest.relative_to(WIKIHUB)),
            'action': 'mechanical merge (refs+aliases+merged_from), LLM body merge pending',
        })
        print(f'[merge] cross-category: archived {con_path.stem}, merged refs+aliases into {ent_path.stem}')
    
    # Save results
    result = {
        'applied': applied,
        'errors': errors,
        'count': len(applied),
    }
    out_path = WIKI / '_lint' / '_fixes_applied.json'
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    
    print(f'\nTotal merges applied: {len(applied)}')
    print(f'Errors: {len(errors)}')

if __name__ == '__main__':
    main()
