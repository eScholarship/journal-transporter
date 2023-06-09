"""
Abstract superclass for progress reporters.

Progress reporters are designed to flexibly accept progress amounts and messages, displaying
the content appropriate to the amount of feedback desired by the user.

Updates are typically split between 3 types:
    MAJOR: A new top-level operation.
    MINOR: A suboperation of a MAJOR update.
    DETAIL: Tracks progress on tasks within MINOR suboperations.

The general workflow is:
    - When the transfer handler starts a new top-level operation, it submits a MAJOR update. In
        non-verbose mode, this creates a new progress bar with a message. The length of this bar
        is equal to the number of suboperations within the top-level operation. In verbose mode,
        it will print a message that the operation is starting.
    - When the handler starts in on a suboperation, if submits a MINOR update. In non-verbose mode,
        a portion of the progress bar will be filled in by the MINOR update, and the message
        is displayed. In verbose mode, this creates a new progress bar.
    - When the handler completes a task within the suboperation, it submits a DETAIL update. In
        non-verbose mode, this simply updates the progress value in the progress bar by an amount
        equal to the progress in the suboperation divided by the length of the suboperation. In
        verbose mode, this fills the suboperation progress bar by the provided amount, and updates
        the message.

There is also the DEBUG type, which does not display progress bars, but instead outputs a
(potentially very) verbose log.
"""
# journal_transporter/progress/abstract_progress_reporter.py

from abc import ABC, abstractmethod
from typing import Any
from datetime import datetime
from pprint import PrettyPrinter
import textwrap

from journal_transporter.progress.progress_update_type import ProgressUpdateType
from journal_transporter.transfer.exceptions import ServerResponseError


class AbstractProgressReporter(ABC):

    def __init__(self, interface: Any, init_message: str = None, start: int = 0, verbose: bool = False,
                 debug: bool = False, log: str = "n", on_error: str = "i", **args) -> None:
        """
        Initializes the progress reporter.

        Parameters:
            interface: Any
                An object that handles updating the UI with current progress.
            init_message: str, optional
                Message to show on initialization.
            start: int, optional
                The initial value for progress on the first bar.
            verbose: bool, optional
                If True, creates new progress counters for every journal. Else, one per operation.
            debug: bool, optional
                If True, foregoes progress bars in favor of (very) verbose debug output.
            log: str, optional
                The log setting to use: n/none (default), e/error, or d/debug
            on_error: str, optional
                Error handlign setting to use: i/interactive (default), c/continue, or a/abort
            args: **kwargs
                Arbitrary implementation-specific kwargs
        """
        self.interface = interface
        self.debug_mode = debug
        self.log_debug = log in ["d", "debug"]
        self.log_error = log in ["e", "error"]
        self.log_file = None
        self.needs_log_file = self.log_debug or self.log_error
        self.on_error = on_error
        self.verbose_mode = verbose
        self.progress = start
        self.message = init_message
        self.progress_length = 100
        self.setup()

    def setup(self, **args):
        """
        Optionally, handle any implementation-specific initialization.
        """
        pass

    def update(self, update_type: ProgressUpdateType = ProgressUpdateType.DETAIL, progress: int = None,
               message: str = None, length: int = 100, debug_message: str = None, **args) -> None:
        """
        Updates progress and message, and updates the UI.

        The logic for this process varies significantly based on update_type.

        Parameters:
            update_type: ProgressUpdateType, optional
                The type of update being provided. Used so the reporter knows if/how to display it.
            progress: int, optional
                The total progress of the current bar.
            message: str, optional
                A new message to display.
            length: int, optional
                The length of the current progress bar. Only used if this generates a new progress
                bar, based on settings and update_type.
            debug_message: str, optional
                If debug mode is enabled, debug message will display if provided, else message. This
                provides a way to provide more verbose output for debug mode.
        """
        if self.debug_mode:
            # If debug mode is on, skip the progress bars and just print the message.
            return self._handle_debug(debug_message or message, update_type)
        elif update_type is not ProgressUpdateType.DEBUG:
            if update_type is ProgressUpdateType.MAJOR:
                if self.verbose_mode:
                    # If verbose, print the message. Progress bars will be generated by minor updates.
                    self._print_message(message)
                else:
                    # If not verbose, create a progress bar that will span the entire operation.
                    self.subtask_length = None
                    self.message = message
                    self.progress_length = length
                    self._new_progress_bar(length, message, progress)
            elif update_type is ProgressUpdateType.MINOR:
                if self.verbose_mode:
                    # If verbose, create a progress bar for this suboperation.
                    self.progress_length = length
                    self.message = message
                    self._new_progress_bar(length, before_message=message)
                else:
                    # If not verbose, update the major progress bar progress and label.
                    self.subtask_length = length
                    if progress:
                        self.set_progress(progress)
                    if message:
                        self.message = message
                        self.set_message(message)
                    self._update_interface()
            elif update_type is ProgressUpdateType.DETAIL:
                # Update progress. If verbose, also update the progress bar label.
                if hasattr(self, "subtask_length") and self.subtask_length:
                    weighted_progress = (progress / self.subtask_length)
                else:
                    weighted_progress = progress

                if progress:
                    self.set_progress(weighted_progress)
                if message and self.verbose_mode:
                    self.message = message
                    self.set_message(message)
                self._update_interface()

        if self.log_debug:
            self.__log_debug(debug_message or message)

    def major(self, message: str = None, length: int = 100, debug_message: str = None) -> None:
        """
        Shortcut for update(ProgressUpdateType.MAJOR...).

        Parameters:
            message: str
                Message to display.
            length: int
                Length of the new progress bar.
            debug_message: str, optional
                Debug message to display if in debug mode.
        """
        return self.update(ProgressUpdateType.MAJOR, message=message, debug_message=debug_message, length=length)

    def minor(self, progress: int = None, message: str = None, length: int = 100, debug_message: str = None) -> None:
        """
        Shortcut for update(ProgressUpdateType.MINOR...).

        Parameters:
            progress: int, optional
                Total progress of the current minor task.
            message: str, optional
                Message to display.
            length: int, optional
                Length of the new progress bar, if in verbose mode.
            debug_message: str, optional
                Debug message to display if in debug mode.
        """
        return self.update(ProgressUpdateType.MINOR, progress=progress, message=message, length=length,
                           debug_message=debug_message)

    def detail(self, progress: int = None, message: str = None, debug_message: str = None) -> None:
        """
        Shortcut for update(ProgressUpdateType.DETAIL...).

        Parameters:
            progress: int, optional
                Total progress of the current minor task.
            message: str, optional
                Message to display.
            debug_message: str, optional
                Debug message to display if in debug mode.
        """
        return self.update(ProgressUpdateType.DETAIL, progress=progress, message=message, debug_message=debug_message)

    def debug(self, message: str) -> None:
        """
        Shortcut for update(ProgressUpdateType.DEBUG...).

        Parameters:
            debug_message: str, optional
                Debug message to display if in debug mode.
        """
        return self.update(ProgressUpdateType.DEBUG, debug_message=message)

    def report_error(self, error: Exception, context: dict = {}) -> str:
        """
        Concrete wrapper for getting a user response to an error.

        Paramters:
            error: Exception
                The error raised
            context: dict
                Error context to display

        Returns:
            str: The user response
        """
        if self.on_error in ["c", "continue"]:
            response = "continue"
        elif self.on_error in ["a", "abort"]:
            response = "abort"
        else:
            response = self._get_error_response(error, context)

        if self.log_error:
            self.__log_error(error, context)

        return response

    @abstractmethod
    def _get_error_response(error: Exception, context: dict) -> str:
        """
        Report an error to the UI for user input.

        Must be implemented by subclass, as it's UI specific.

        Paramters:
            error: Exception
                The error raised
            context: dict
                Error context to display

        Returns:
            str: The user response
        """
        pass

    def error(self, message: str, fatal: bool = False) -> None:
        """
        Reports an error to the UI.

        This method does not stop any processes, it just displays them! The exception must
        be handled elsewhere.

        Parameters:
            message: str
                The message to display.
            fatal: bool, optional
                If True, end the current progress bar and print the message as deeply red as possible.
        """
        self._close_progress_bar()
        self._print_message(message, error=True, fatal_error=fatal)

    def set_progress(self, progress: int) -> None:
        """
        Sets the current progress.

        Parameters:
            progress: int
                The total progress of the current bar.
        """
        self.progress = progress

    def set_message(self, message: str) -> None:
        """
        Updates the application-specific UI with a progress message.

        Parameters:
            message: str
                The message to display.
        """
        self.message = message

    @abstractmethod
    def clean_up(self) -> None:
        """
        Cleans up any progress bars for a clean exit.
        """
        pass

    # Protected methods

    @abstractmethod
    def _update_interface(self, **args) -> None:
        """
        Updates the application-specific UI based on current progress.

        Must be implemented in sublcass. Any kwargs must be optional, as this method is called
        without arguments on initialization.

        Parameters:
            args: dict
                Arbitrary parameters used in subclass.
        """
        pass

    @abstractmethod
    def _new_progress_bar(self, length: int, before_message: str = None, bar_init_message: str = None,
                          start: int = 0) -> None:
        """
        Tells the interface to end the current progress bar and create a new one.

        Parameters:
            length: int
                The length of the progress bar.
            before_message: str, optional
                A message to display before rendering the new progress bar.
            bar_init_message: str, optional
                A message to show on initialization of the new bar.
            start: int, optional
                The initial value for progress on the new bar.
        """
        pass

    @abstractmethod
    def _close_progress_bar(self) -> None:
        """
        Ends the current progress bar, regardless of completion.

        Needed for error handling, but can be re-used for setting up new progress bars.
        """
        pass

    def _handle_debug(self, message: str, update_type: ProgressUpdateType = ProgressUpdateType.DEBUG) -> None:
        """
        Handles debug output.

        Typically, this will involve simply printing the message without a progress bar, but
        can vary based on implementation.

        Parameters:
            update_type: ProgressUpdateType
                The type of update. Generally, debug should print all, but may use different
                formatting based on implementation.
            message: str
                The message to be printed.
        """
        if self.debug_mode and message:
            debug_text = f"{self._now()} -- {message}"
            self._print_message(debug_text)

    def __log_debug(self, message) -> None:
        """
        Writes a debug message to the log, if debug logging is on.

        Parameters:
            message: str
                The message to be written.
        """
        if self.log_debug:
            self.__write_to_log(message)

    def __log_error(self, error: Exception, context: dict) -> None:
        """
        Writes an error message to the log, if error logging is on.

        Parameters:
            message: str
                The message to be written
        """
        if self.log_error:
            error_info = self.__error_info(error)
            message = str(error_info) + "\n" + str(PrettyPrinter(indent=2).pprint(context))
            self.__write_to_log(message)

    def __write_to_log(self, message) -> None:
        """
        Writes a message to the log file.

        Parameters:
            message: str
                The message to be written
        """
        if self.log_file and message:
            text = f"{self._now()} -- {message}"
            with open(self.log_file, "a") as log:
                log.write(text + "\n")

    @abstractmethod
    def _print_message(self, message: str, **kwargs) -> None:
        """
        Prints a message to the interface outside of or separate from the progress bar.

        Parameters:
            message: str
                The message to display.
            kwargs: dict
                Arbitrary options to be passed to implementation (i.e. for output formatting)
        """
        pass

    def _now(self) -> str:
        """Returns the current timestamp in ISO format."""
        return datetime.now().strftime("%Y-%m-%dT%H:%M:%S")

    # Private methods

    def __should_update(self, update_type: ProgressUpdateType) -> bool:
        """Should the reporter update the interface for a given update type?"""
        if update_type is ProgressUpdateType.MAJOR:
            return True
        elif update_type is ProgressUpdateType.MINOR:
            return self.verbose
        elif update_type is ProgressUpdateType.DEBUG:
            return self.debug

    def __error_info(self, error: Exception) -> str:
        if isinstance(error, ServerResponseError):
            return textwrap.dedent(
                f"Server returned an error response:"
                f"Status {error.response.status_code} - {error.response.reason}"
                f"{error.response.text}"
            )
        else:
            return error.args[0]
