import difflib, re
import pandas
from typing import Iterator

COL_LABEL_OPS, COL_LABEL_LINE_CONTENT = 'Ops', 'Line'
COL_LABEL_LINE_NUM_1, COL_LABEL_LINE_NUM_2, COL_LABEL_LINE_TAG =  'Line num 1', 'Line num 2', 'Line tag'
TAG_CHANGE_BOTH, TAG_CHANGE_1ST, TAG_CHANGE_2ND = 'chg_both', 'chg_1','chg_2'
TAG_REMOVE_FROM_1ST, TAG_REMOVE_FROM_2ND = 'extra_1', 'extra_2'
TAG_IDENTICAL = 'same'

class DifferO(difflib.Differ):
    def __init__(self, cutoff:float=0.75, linejunk=None, charjunk=None):
        """
        Overidden Differ class. Exactly the same as the original Differ, except taking in a changable cutoff value for line-to-line similarity.
        
        Args:
            cutoff (float, optional): Cutoff value for line-to-line similarity. Defaults to 0.75. Will be truncated into range [0.0, 1.0]. 
            linejunk (callable, optional): A filter function for junk lines. More documentation please see inside difflib.
            charjunk (callable, optional): A filter function for junk characters. More documentation please see inside difflib.
        """
        self.linejunk = linejunk
        self.charjunk = charjunk
        # Truncate the input cutoff to be in [0.0, 1.0]
        self.cutoff = min(max(cutoff, 0.0), 1.0)
    
    def _fancy_helper(self, a, alo, ahi, b, blo, bhi):
        """
        Exactly the same as the original _fancy_helper(..) except using self._fancy_replace(..)
        """
        g = []
        if alo < ahi:
            if blo < bhi:
                g = self._fancy_replace(a, alo, ahi, b, blo, bhi)
            else:
                g = super()._dump('-', a, alo, ahi)
        elif blo < bhi:
            g = super()._dump('+', b, blo, bhi)
  
        yield from g
  
    def _fancy_replace(self, a, alo, ahi, b, blo, bhi):
      """
      Override the original _fancy_replace(..), with very little change. Just making the ratio changable.
      Refer to difflib.Differ for more documentation.
      """

      # don't synch up unless the lines have a similarity score of at
      # least cutoff; best_ratio tracks the best score seen so far
      cutoff = self.cutoff
      best_ratio = min(max((cutoff - 0.01), 0.0), 0.99)
      cruncher = difflib.SequenceMatcher()
      eqi, eqj = None, None   # 1st indices of equal lines (if any)

      # search for the pair that matches best without being identical
      # (identical lines must be junk lines, & we don't want to synch up
      # on junk -- unless we have to)
      for j in range(blo, bhi):
          bj = b[j]
          cruncher.set_seq2(bj)
          for i in range(alo, ahi):
              ai = a[i]
              if ai == bj:
                  if eqi is None:
                      eqi, eqj = i, j
                  continue
              cruncher.set_seq1(ai)
              # computing similarity is expensive, so use the quick
              # upper bounds first -- have seen this speed up messy
              # compares by a factor of 3.
              # note that ratio() is only expensive to compute the first
              # time it's called on a sequence pair; the expensive part
              # of the computation is cached by cruncher
              if cruncher.real_quick_ratio() > best_ratio and \
                    cruncher.quick_ratio() > best_ratio and \
                    cruncher.ratio() > best_ratio:
                  best_ratio, best_i, best_j = cruncher.ratio(), i, j
      if best_ratio < cutoff:
          # no non-identical "pretty close" pair
          if eqi is None:
              # no identical pair either -- treat it as a straight replace
              yield from super()._plain_replace(a, alo, ahi, b, blo, bhi)
              return
          # no close pair, but an identical pair -- synch up on that
          best_i, best_j, best_ratio = eqi, eqj, 1.0
      else:
          # there's a close pair, so forget the identical pair (if any)
          eqi = None

      # a[best_i] very similar to b[best_j]; eqi is None iff they're not
      # identical

      # pump out diffs from before the synch point
      yield from self._fancy_helper(a, alo, best_i, b, blo, best_j)

      # do intraline marking on the synch pair
      aelt, belt = a[best_i], b[best_j]
      if eqi is None:
          # pump out a '-', '?', '+', '?' quad for the synched lines
          atags = btags = ""
          cruncher.set_seqs(aelt, belt)
          for tag, ai1, ai2, bj1, bj2 in cruncher.get_opcodes():
              la, lb = ai2 - ai1, bj2 - bj1
              if tag == 'replace':
                  atags += '^' * la
                  btags += '^' * lb
              elif tag == 'delete':
                  atags += '-' * la
              elif tag == 'insert':
                  btags += '+' * lb
              elif tag == 'equal':
                  atags += ' ' * la
                  btags += ' ' * lb
              else:
                  raise ValueError('unknown tag %r' % (tag,))
          yield from super()._qformat(aelt, belt, atags, btags)
      else:
          # the synch pair is identical
          yield '  ' + aelt

      # pump out diffs from after the synch point
      yield from self._fancy_helper(a, best_i+1, ahi, b, best_j+1, bhi)

    def get_line_op_blocks(self, line_ops:list[str]):
        # This pattern means both missing/extra characters in line2
        pattern_chg_both = "-?+?"
        # This pattern means only missing characters in line2
        pattern_chg_1 = "-?+"
        # This pattern means only extra characters in line2
        pattern_chg_2 = "-+?"

        joined = ''.join(line_ops)

        both = re.finditer(re.escape(pattern_chg_both), joined)
        both = [match.start() for match in both]

        chg_1 = re.finditer(re.escape(pattern_chg_1), joined)
        chg_1 = [match.start() for match in chg_1]
        # Exclude intersect elements from the list "both" because we don't want to double count "-?+" in "-?+?"
        chg_1 = [e for e in chg_1 if e not in both]

        chg_2 = re.finditer(re.escape(pattern_chg_2), joined)
        chg_2 = [match.start() for match in chg_2]

        return {TAG_CHANGE_BOTH:both, TAG_CHANGE_1ST: chg_1, TAG_CHANGE_2ND: chg_2}
    
    def seperate_line_ops(self, compare_result:Iterator):
        ops, line_contents = [], []
        
        for line in compare_result:
            ops.append(line[:1])
            line_contents.append(line[2:])

        line_num1_list, line_num2_list, line_tags = [], [], []
        extra_lines, missing_lines = [], []
        i, line_num1, line_num2 = 0, 1, 1
        blocks = self.get_line_op_blocks(ops)
        while i in range(len(ops)):
            if i in blocks[TAG_CHANGE_BOTH]:
                # This means both have to be changed to become same, "-?+?" pattern
                # Append (line_num1, -1)           to row ops[i]
                #        (-1,        -1)           to row ops[i+1]
                #        (-1,        line_num2)    to row ops[i+2]
                #        (-1,        -1)           to row ops[i+3]
                line_num1_list.extend([line_num1, -1, -1, -1])
                line_num2_list.extend([-1, -1, line_num2, -1])
                line_tags.extend([TAG_CHANGE_BOTH, TAG_CHANGE_BOTH, TAG_CHANGE_BOTH, TAG_CHANGE_BOTH])
                # Increment line pointers in both original paragraphs
                line_num1 += 1
                line_num2 += 1
                # Increment loop counter to skip these 4 lines
                i += 4
            elif i in blocks[TAG_CHANGE_1ST]:
                # This means "-?+" pattern
                # Append (line_num1, -1)           to row ops[i]
                #        (-1,        -1)           to row ops[i+1]
                #        (-1,        line_num2)    to row ops[i+2]
                line_num1_list.extend([line_num1, -1, -1])
                line_num2_list.extend([-1, -1, line_num2])
                line_tags.extend([TAG_CHANGE_1ST, TAG_CHANGE_1ST, TAG_CHANGE_1ST])
                # Increment line pointers in both original paragraphs
                line_num1 += 1
                line_num2 += 1
                # Increment loop counter to skip these 3 lines
                i += 3
            elif i in blocks[TAG_CHANGE_2ND]:
                # This means "-+?" pattern
                # Similar to above case
                line_num1_list.extend([line_num1, -1, -1])
                line_num2_list.extend([-1, line_num2, -1])
                line_tags.extend([TAG_CHANGE_2ND, TAG_CHANGE_2ND, TAG_CHANGE_2ND])
                # Increment line pointers in both original paragraphs
                line_num1 += 1
                line_num2 += 1
                # Increment loop counter to skip these 3 lines
                i += 3
            else:
                if ops[i] == '-':
                    # This means missing line in paragraph 2
                    # Add similar info to line i
                    line_num1_list.append(line_num1)
                    line_num2_list.append(-1)
                    line_tags.extend([TAG_REMOVE_FROM_1ST])
                    missing_lines.append(line_num1)
                    # Only increment line pointer in paragraph 1
                    line_num1 += 1
                elif ops[i] == '+':
                    # This means extra line in paragraph 2
                    # Add similar info to line i
                    line_num1_list.append(-1)
                    line_num2_list.append(line_num2)
                    line_tags.extend([TAG_REMOVE_FROM_2ND])
                    extra_lines.append(line_num2)
                    # Only increment line pointer in paragraph 2
                    line_num2 += 1
                else:
                    # This means same line in both paragraphs
                    # Add similar info to line i
                    line_num1_list.append(line_num1)
                    line_num2_list.append(line_num2)
                    line_tags.extend([TAG_IDENTICAL])
                    # Increment line pointers in both original paragraphs
                    line_num1 += 1
                    line_num2 += 1
                i += 1
        
        df = pandas.DataFrame(list(zip(ops, line_contents, line_num1_list, line_num2_list, line_tags)), columns=[COL_LABEL_OPS, COL_LABEL_LINE_CONTENT, COL_LABEL_LINE_NUM_1, COL_LABEL_LINE_NUM_2, COL_LABEL_LINE_TAG])
        return df, blocks, missing_lines, extra_lines
    