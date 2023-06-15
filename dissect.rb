els = [1, 5, 1, 2, 1, 3, 0, 0, 4, 5, 1, 1, 1, 4, 0, 3, 1, 1, 0, 0, 0, 3, 1, 4, 0, 0, 2, 3, 1, 5, 0, 3, 1, 6, 0, 3, 1, 7, 0, 0, 8, 8, 4, 97, 122, 47, 47, 1, 8, 0, 1, 0, 0, 7, 27, 2, 110, 110, 2, 97, 97, 2, 118, 118, 2, 40, 40, 2, 34, 34, 2, 47, 47, 1, 8, 2, 34, 34, 2, 41, 41, 0, 0, 6, 21, 2, 105, 105, 2, 110, 110, 2, 102, 102, 2, 111, 111, 2, 40, 40, 1, 9, 2, 41, 41, 0, 0, 5, 20, 2, 116, 116, 2, 40, 40, 1, 9, 2, 58, 58, 2, 32, 32, 1, 10, 2, 41, 41, 0, 0, 10, 3, 1, 11, 0, 3, 1, 12, 0, 3, 1, 13, 0, 3, 1, 14, 0, 0, 11, 34, 2, 35, 35, 4, 48, 57, 97, 102, 4, 48, 57, 97, 102, 4, 48, 57, 97, 102, 4, 48, 57, 97, 102, 4, 48, 57, 97, 102, 4, 48, 57, 97, 102, 0, 0, 15, 10, 6, 97, 122, 95, 95, 32, 32, 1, 15, 0, 8, 6, 97, 122, 95, 95, 32, 32, 0, 0, 9, 3, 1, 15, 0, 0, 16, 14, 10, 32, 32, 9, 9, 33, 33, 35, 91, 93, 126, 1, 16, 0, 1, 0, 0, 13, 9, 2, 34, 34, 1, 16, 2, 34, 34, 0, 0, 17, 6, 2, 48, 57, 1, 17, 0, 4, 2, 48, 57, 0, 0, 12, 3, 1, 17, 0, 0, 18, 13, 2, 116, 116, 2, 114, 114, 2, 117, 117, 2, 101, 101, 0, 16, 2, 102, 102, 2, 97, 97, 2, 108, 108, 2, 115, 115, 2, 101, 101, 0, 0, 14, 3, 1, 18, 0, 0, 3, 4, 2, 10, 10, 0, 0, 65535]

$rule_positions = {}
$rule_alternates = {}

def f(e)
  "\x1b[1;34m#{format("%04x", e)}\x1b[0m"
end

$ids = []
$pos = 0

def read_rule(els, indent = '')
  $pos += 1
  rule_id = els.shift
  puts rule_id
  return(false) if rule_id == 0xffff

  $ids << rule_id
  $rule_positions[rule_id] = $pos-1
  puts(indent + "rule #{rule_id} (#{f(rule_id)}) {")

  alt_n = 0
  while read_alt(rule_id, els, indent+'  ', alt_n)
    alt_n += 1
  end
  puts(indent + "} (#{f(0)})")

  true
end

def read_alt(rule_id, els, indent, alt_n)
  $pos += 1
  alt_size = els.shift
  return(false) if alt_size == 0

  puts(indent + "alternate (len=#{f(alt_size)}) {")

  while read_sym(rule_id, els, indent+'  ', alt_n)
  end

  puts(indent + "} (#{f(0)})")

  true
end

def read_sym(rule_id, els, indent = '', alt_n)
  spos = $pos
  $pos += 1
  sym_size = els.shift

  $rule_alternates[rule_id] ||= []
  $rule_alternates[rule_id][alt_n] ||= []

  case sym_size
  when 0
    return(false)
  when 1
    $pos += 1
    id = els.shift
    puts(indent + "sym (len=#{f(sym_size)}) => ref rule #{id} (#{f(id)})")
    $rule_alternates[rule_id][alt_n] << {
      pos: spos,
      rule: id,
    }
  else
    puts(indent + "sym (len=#{f(sym_size)}) {")
    ranges = []
    sym_size.times.each_slice(2) do |from, to|
      $pos += 2
      from = els.shift
      to = els.shift
      if from == to
        ranges << from.chr
      else
        ranges << ((from.chr)..(to.chr))
      end
      puts(indent+"  chars [#{f(from)}-#{f(to)}]")
    end
    $rule_alternates[rule_id][alt_n] << {
      pos: spos,
      chars: ranges,
    }
    puts(indent + "}")
  end
  true
end

puts("grammar {")
while read_rule(els, '  ')
end
puts "} (#{f(0xffff)})"

puts $rule_positions.inspect
$rule_alternates.each do |rule_id, alts|
  rule_pos = $rule_positions[rule_id]
  puts(format("RULE #%-4s                         @ %d", rule_id, rule_pos))
  alts.each.with_index do |alt, n|
    puts "  ------------" unless n == 0
    alt.each do |sym|
      if sym.key?(:rule)
        puts(format("    - rule#%-23s @ %d", sym[:rule].to_s, sym[:pos]))
      else
        puts(format("    - %-28s @ %d", sym[:chars].inspect, sym[:pos]))
      end
    end
  end
end

# puts $rule_alternates.inspect
