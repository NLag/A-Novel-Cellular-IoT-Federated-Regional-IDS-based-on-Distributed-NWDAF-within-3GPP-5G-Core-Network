#ifndef __NEXT_PROG_RULE_MAP_H__
#define __NEXT_PROG_RULE_MAP_H__

#include <bpf_helpers.h>
#include <linux/bpf.h>
#include <types.h>
#include <next_prog_rule_key.h>

#define MAX_LENGTH 5000  // 10

/*
 *   +------------------------------------------------------+
 *   |                   m_next_rule_prog                   |
 *   +--------------------------+---------------------------+
 *   |        Key               |                    Value  |
 *   +--------------------------+---------------------------+
 *   |                          |                           |
 *   |    u32 FAR_ID            |  u32 FAR File Descriptor  |
 *   |                          |                           |
 *   +--------------------------+---------------------------+
 */

struct {
  __uint(type, BPF_MAP_TYPE_PROG_ARRAY);
  __uint(max_entries, MAX_LENGTH);  // 10,
  __type(key, u32);
  __type(value, s32);
} m_next_rule_prog SEC(".maps");

struct {
  __uint(type, BPF_MAP_TYPE_HASH);
  __uint(max_entries, MAX_LENGTH);
  __type(key, struct next_rule_prog_index_key);
  __type(value, u32);
} m_next_rule_prog_index SEC(".maps");

// BPF_ANNOTATE_KV_PAIR(m_next_rule_prog, u32, s32);

#endif  // __NEXT_PROG_RULE_MAP_H__
