from gsheet_manager import GSheetManager
import tqdm


class GSheetWithHeader(GSheetManager):
    @property
    def headers(self):
        return self.local_sheet_values[0]

    def clear_worksheet(self):
        self._worksheet.clear()

    def get_data_list(self):
        self.sync_from_remote()
        data_list = []
        for row in self.local_sheet_values[1:]:
            data_list.append(dict(zip(self.headers, row)))
        return data_list

    @GSheetManager.batch_sync_with_remote
    def _write_headers(self, headers, start_row_idx=0):
        current_row_idx = start_row_idx
        for header_idx, header_name in enumerate(headers):
            self._set_buffer_cells(python_row_idx=start_row_idx,
                                   python_col_idx=header_idx,
                                   value=header_name)
        current_row_idx += 1
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
        return current_row_idx

    @GSheetManager.batch_sync_with_remote
    def write_rows(self, rows, empty_sheet=False, headers=None, write_headers=True, start_row_idx=0, batch_size=1000):
        if empty_sheet:
            self.clear_worksheet()

        if headers is None:
            headers = self.headers

        if write_headers:
            current_row_idx = self._write_headers(headers, start_row_idx=start_row_idx)
        else:
            current_row_idx = start_row_idx

        for idx in tqdm.tqdm(range(0, len(rows), batch_size)):
            current_row_idx = self._write_batch(data_list_batch=rows[idx:idx + batch_size],
                                                headers=headers, start_row_idx=current_row_idx)
        return current_row_idx
