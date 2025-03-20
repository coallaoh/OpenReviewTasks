import logging
from gsheet_manager import GSheetManager
import tqdm


class GSheetWithHeader(GSheetManager):
    @property
    def headers(self):
        return self.local_sheet_values[0]

    def clear_worksheet(self):
        self._worksheet.clear()
        logging.info("Worksheet cleared")

    def get_data_list(self):
        self.sync_from_remote()
        data_list = []
        for row in self.local_sheet_values[1:]:
            data_list.append(dict(zip(self.headers, row)))
        logging.info(f"Retrieved {len(data_list)} rows of data")
        return data_list

    @GSheetManager.batch_sync_with_remote
    def _write_headers(self, headers, start_row_idx=0):
        current_row_idx = start_row_idx
        for header_idx, header_name in enumerate(headers):
            self._set_buffer_cells(python_row_idx=start_row_idx,
                                   python_col_idx=header_idx,
                                   value=header_name)
        current_row_idx += 1
        logging.debug(f"Headers written starting at row {start_row_idx}")
        return current_row_idx

    @GSheetManager.batch_sync_with_remote
    def _write_batch(self, data_list_batch, headers, start_row_idx):
        current_row_idx = start_row_idx
        for row_idx, d in enumerate(data_list_batch):
            for header_idx, header_name in enumerate(headers):
                self._set_buffer_cells(python_row_idx=start_row_idx + row_idx,
                                       python_col_idx=header_idx,
                                       value=d[header_name])
            current_row_idx += 1
        logging.debug(f"Batch of {len(data_list_batch)} rows written starting at row {start_row_idx}")
        return current_row_idx

    @GSheetManager.batch_sync_with_remote
    def write_rows(self, rows, empty_sheet=False, headers=None, write_headers=True, start_row_idx=0, batch_size=1000):
        if empty_sheet:
            self.clear_worksheet()
            logging.info("Sheet emptied before writing")

        if headers is None:
            headers = self.headers

        if write_headers:
            current_row_idx = self._write_headers(headers, start_row_idx=start_row_idx)
        else:
            current_row_idx = start_row_idx

        total_rows = len(rows)
        for idx in tqdm.tqdm(range(0, total_rows, batch_size)):
            current_row_idx = self._write_batch(data_list_batch=rows[idx:idx + batch_size],
                                                headers=headers, start_row_idx=current_row_idx)
        logging.info(f"Total of {total_rows} rows written to sheet")
        return current_row_idx

    @GSheetManager.batch_sync_with_remote
    def write_cells(self, where, what, overwrite=False):
        updates_count = 0
        for where_, what_ in zip(where, what):
            try:
                python_row_idx = next(i for i, row in enumerate(self.local_sheet_values) 
                              if all(row[self.headers.index(k)] == v for k, v in where_.items()))
            except StopIteration:
                logging.warning(f"No matching row found for conditions: {where_}")
                continue
            
            for col_header, value in what_.items():
                try:
                    python_col_idx = self.headers.index(col_header)
                except ValueError:
                    logging.warning(f"Column header '{col_header}' not found in headers")
                    continue
                
                current_value = self.local_sheet_values[python_row_idx][python_col_idx]
                if current_value and current_value != value and not overwrite:
                    logging.warning(f"Skipping non-empty cell at row {python_row_idx + 1}, column {col_header}. Current value: '{current_value}', New value: '{value}'")
                    continue
                
                if current_value and current_value != value and overwrite:
                    logging.info(f"Overwriting cell at row {python_row_idx + 1}, column {col_header}. Old value: '{current_value}', New value: '{value}'")
                
                self._set_buffer_cells(python_row_idx=python_row_idx,
                                       python_col_idx=python_col_idx, 
                                       value=value)
                updates_count += 1
                
        logging.info(f"Updated {updates_count} cells in the sheet")