import bisect
import collections


class BreakpointDatabase(object):
    def __init__(self, breakpoints, id_col='breakpoint_id'):
        self.positions = collections.defaultdict(list)
        self.break_ids = collections.defaultdict(set)

        for row in breakpoints.to_dict('records'):
            for side in ('1', '2'):
                self.positions[(row['chromosome_' + side], row['strand_' + side])].append(row['position_' + side])
                self.break_ids[(row['chromosome_' + side], row['strand_' + side], row['position_' + side])].add(
                    (row[id_col], side))

        # dedup positions: break_ids already aggregates every id at a given
        # position, so each unique position only needs to be visited once in
        # query(). Without this, co-located calls in dense regions make the
        # window scan re-emit the same id sets repeatedly (quadratic blow-up).
        for key in self.positions.keys():
            self.positions[key] = sorted(set(self.positions[key]))

    def query(self, row, extend=0):
        exclusion = row['breakpoint_id']
        # raise Exception(row)
        matched_ids = list()

        for side in ('1', '2'):
            chrom_strand_positions = self.positions[(row['chromosome_' + side], row['strand_' + side])]
            idx = bisect.bisect_left(chrom_strand_positions, row['position_' + side] - extend)
            side_matched_ids = list()

            while idx < len(chrom_strand_positions):
                pos = chrom_strand_positions[idx]
                dist = abs(pos - row['position_' + side])

                if pos >= row['position_' + side] - extend and pos <= row['position_' + side] + extend:
                    for break_id in self.break_ids[(row['chromosome_' + side], row['strand_' + side], pos)]:
                        side_matched_ids.append((break_id, dist))

                if pos > row['position_' + side] + extend:
                    break
                idx += 1
            matched_ids.append(side_matched_ids)

        # An id is a match if it appears in the side-1 window and the side-2
        # window with opposite side labels. Hash-join the two sides instead of
        # the O(m1*m2) nested loop; the result is the same id set.
        side0_sides = collections.defaultdict(set)
        for (break_id, side), _dist in matched_ids[0]:
            side0_sides[break_id].add(side)

        ids = {exclusion}
        for (break_id, side), _dist in matched_ids[1]:
            if break_id == exclusion:
                continue
            other_sides = side0_sides.get(break_id)
            if other_sides and any(s != side for s in other_sides):
                ids.add(break_id)

        return sorted(ids)


