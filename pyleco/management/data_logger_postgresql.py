#
# This file is part of the PyLECO package.
#
# Copyright (c) 2023-2023 PyLECO Developers
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
#

import logging
import datetime
from typing import Any

import psycopg2  # type: ignore[import-untyped]

from .data_logger import DataLogger


log = logging.getLogger(__name__)
log.addHandler(logging.StreamHandler())  # log to stderr
log.setLevel(logging.INFO)


class DataLoggerSQL(DataLogger):
    """A data logger, which writes every datapoint into a postgreSQL database."""

    def __init__(self, name: str,
                 host: str = 'HOST-NAME', port: int = 5432, database: str = 'DATABASE-NAME',
                 user: str = 'USER-NAME', password: str = 'USER-PASSWORD', table=None, **kwargs):
        super().__init__(name=name, **kwargs)
        self.connection_data = dict(host=host, port=port, database=database, user=user,
                                    password=password)
        if table is None:
            raise ValueError("Table must not be empty.")
        self.table = table
        self.tries = 0
        self.connect_database()

    def make_data_point(self):
        super().make_data_point()
        self.write_database(self.last_datapoint)
        # TODO delete data, if too much?

    def connect_database(self):
        """(Re)Establish a connection to the database for storing data."""
        try:
            self.database.close()
            del self.database
        except AttributeError:
            pass  # no database present
        try:
            self.database = psycopg2.connect(**self.connection_data, connect_timeout=5)
        except Exception as exc:
            log.exception("Database connection error.", exc_info=exc)

    def write_database(self, data: dict[str, Any]):
        """Write the data in the database with the timestamp."""
        try:  # Check connection to the database and reconnect if necessary.
            database = self.database
        except AttributeError:
            if self.tries < 10:
                self.tries += 1
            else:
                self.connect_database()
                self.tries = 0
            return  # No database connection existing.
        columns = "timestamp"
        for key in data.keys():
            columns += f", {key.lower()}"
        length = len(data)
        with database.cursor() as cursor:
            try:
                cursor.execute(f"INSERT INTO {self.table} ({columns}) VALUES (%s{', %s' * length})",
                               (datetime.datetime.now(), *data.values()))
            except (psycopg2.OperationalError, psycopg2.InterfaceError):
                self.connect_database()  # Connection lost, reconnect.
            except Exception as exc:
                log.exception("Database write error.", exc_info=exc)
                database.rollback()
            else:
                database.commit()
