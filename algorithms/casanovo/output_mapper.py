"""Script to convert predicted labels from the original algorithm 
output format to the common data format."""

import argparse
import re
from pyteomics.mztab import MzTab


class OutputMapper:
    REPLACEMENTS = [
        ("C+57.021", "C")  # C is written without Carbamidomethyl modification
    ]
    N_TERM_MOD_PATTERN = r"^([0-9.+-]+)([A-Z])" # find N-term modifications
    
    FILE_IDX_PATTERN = "\[(\d+)\]"
    
    def _transform_match_n_term_mod(self, match: re.Match) -> str:
        """
        Transform representation of amino acids substring matching
        the N-term modification pattern.
        `+n_modAA` -> `A+n_modA`
        
        TODO: define/extend behaviour for `+n_modA+ptm` case -> `A+total_mass`

        Parameters
        ----------
        match : re.Match
            Substring matching the N-term modification pattern.

        Returns
        -------
        transformed_match : str
            Transformed N-term modification pattern representation.
        """
        ptm, aa = match.group(1), match.group(2)
        return aa + ptm
    
    def _transform_match_file_idx(self, match: re.Match) -> str:
        """TODO."""

        file_idx = int(match.group(0)[1:-1])
        return f"F{file_idx - 1}"
    
    def _parse_scores(self, scores: str) -> list[float]:
        """
        Convert per-token scores from a string of float scores 
        separated by ',' to a list of float numbers.
        """
        scores = scores.split(",")
        scores = list(map(float, scores))
        return scores

    def _format_scores(self, scores: list[float]) -> str:
        """
        Write a list of float per-token scores
        into a string of float scores separated by ','.
        """
        return ",".join(map(str, scores))
    
    def format_scan_index(self, scan_index: str) -> str:
        """
        TODO.
        Transform scan index generated by the algorithm to the common format.
        `ms_run[i]:index=j` -> `F[i-1]:j`
        """

        scan_index = re.sub("[a-z=_]", "", scan_index)
        scan_index = re.sub(self.FILE_IDX_PATTERN, self._transform_match_file_idx, scan_index)
        return scan_index
    
    def format_sequence_and_scores(self, sequence: str, aa_scores: str) -> str:
        """
        Convert peptide sequence to the common output data format.
        If it changes the number of tokens in a sequence, 
        adjust per-token algorithm scores accordingly.

        Parameters
        ----------
        sequence : str
            Peptide sequence in the original algorithm output format.
        aa_scores: str
            Algorithm confidence scores for each token in sequence.
            Stored as a string of float scores separated by ','.

        Returns
        -------
        transformed_sequence : str
            Peptide sequence in the common output data format.
        """

        # direct (token-to-token) replacements
        for repl_args in self.REPLACEMENTS:
            sequence = sequence.replace(*repl_args)

        # transform PTM notation:
        # move N-terminus modifications BEYOND 1st AA
        # TODO: check & replacement can be not optimal!
        if re.search(self.N_TERM_MOD_PATTERN, sequence):
            sequence = re.sub(self.N_TERM_MOD_PATTERN, self._transform_match_n_term_mod, sequence)
            
            # transform aa_scores:
            # the N-terminus modification and the next AA are considered 
            # as a single AA+PTM token with a single (aggregated) score
            aa_scores = self._parse_scores(aa_scores)
            aa_scores[1] = (aa_scores[0] + aa_scores[1]) / 2
            aa_scores = aa_scores[1:]
            aa_scores = self._format_scores(aa_scores)

        return sequence, aa_scores
    
    def format_output(self, output_data):
        """TODO."""
        
        if "aa_scores" in output_data.columns:
            output_data[["sequence", "aa_scores"]] = output_data.apply(
                lambda row: self.format_sequence_and_scores(row["sequence"], row["aa_scores"]),
                axis=1,
                result_type="expand",
            )
        
        else:
            output_data["sequence"] = output_data.apply(
                self.format_sequence,
            )
            # TODO: add logic for aa_scores, if they are not provided
            # output_data["aa_scores"] = get_aa_scores(output_data)

        output_data["scan_indices"] = output_data["scan_indices"].apply(
            self.format_scan_index
        )

        return output_data


parser = argparse.ArgumentParser()
parser.add_argument(
    "output_path", help="The path to the algorithm predictions file."
)
args = parser.parse_args()

# read predictions from output file
output_data = MzTab(args.output_path)

output_data = output_data.spectrum_match_table
output_data = output_data.rename(
    {
        "search_engine_score[1]": "score",
        "spectra_ref": "scan_indices",
        "opt_ms_run[1]_aa_scores": "aa_scores",
    },
    axis=1,
)

output_mapper = OutputMapper()
output_data = output_mapper.format_output(output_data)

# save processed predictions to the same file
output_data.to_csv("outputs.csv", index=False)
