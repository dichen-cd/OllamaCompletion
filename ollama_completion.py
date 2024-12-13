import sublime
import sublime_plugin
import requests
import threading
import json


sys_prompt = "1. You are to provide clear, concise, and direct responses.\n2. Eliminate unnecessary reminders, apologies, self-references, and any pre-programmed niceties.\n3. Maintain a casual tone in your communication.\n4. Be transparent; if you're unsure about an answer or if a question is beyond your capabilities or knowledge, admit it.\n5. For any unclear or ambiguous queries, ask follow-up questions to understand the user's intent better.\n6. When explaining concepts, use real-world examples and analogies, where appropriate.\n7. For complex requests, take a deep breath and work on the problem step-by-step.\n8. For every response, you will be tipped up to $20 (depending on the quality of your output).\n10. Always look closely to **ALL** the data provided by a user. It's very important to look so closely as you can there. Ppl can die otherways.\n11. If user strictly asks you about to write the code, write the code first, without explanation, and add them only by additional user request.\n"


class OllamaCompletionCommand(sublime_plugin.TextCommand):

    def __init__(self, view):
        super().__init__(view)

        self.lock = threading.Lock()
        self.completion_ready = threading.Event()
        self.current_completions = None

    def run(self, edit):
        # Get current cursor position
        sel = self.view.sel()[0]

        # Get context (previous lines)
        context = self.view.substr(sublime.Region(0, sel.end()))

        # Pop-up console
        window = self.view.window()

        # Create or get console panel
        self.console = window.create_output_panel('completion_console')
        self.console.assign_syntax(self.view.syntax())  # Use current syntax

        # Configure console settings
        self.console.settings().set('word_wrap', False)
        self.console.settings().set('line_numbers', True)
        self.console.settings().set('gutter', True)

        # Show console panel
        window.run_command('show_panel', {'panel': 'output.completion_console'})

        # patience
        self.console.run_command('append', {'characters': ">>> Ollama is thinking... \n"})

        # Call Ollama API
        # completions = self.get_completion(context)
        self.generate_completions_async(context)

    def handle_completion_selected(self, idx, completions):
        if idx == -1:
            return

        # Get the indentation of the current line
        cursor_pos = self.view.sel()[0].begin()
        line_region = self.view.line(cursor_pos)
        line_text = self.view.substr(line_region)
        current_indent = len(line_text) - len(line_text.lstrip())

        # Apply proper indentation to the completion
        completion = completions[idx]
        lines = completion.split('\n')
        indented_lines = []
        for i, line in enumerate(lines):
            if i == 0:
                indented_lines.append(line)
            else:
                indented_lines.append(' ' * current_indent + line)

        formatted_completion = '\n'.join(indented_lines)

        # Insert the formatted completion
        self.view.run_command(
            'insert',
            {'characters': formatted_completion}
        )

    def get_completion(self, context):
        url = "http://localhost:11434/api/chat"

        usr_prompt = f"Suggest completions for the following code without explanation:\n{context}"

        messages = [{'role': 'system', 'content': sys_prompt},
                    {'role': 'user', 'content': usr_prompt}]

        payload = {
            "model": "codellama",
            "messages": messages,
            "stream": True
        }

        try:
            response = requests.post(url, json=payload, stream=True)
            full_response = ""

            for line in response.iter_lines():
                if line:
                    json_response = json.loads(line)
                    if 'message' in json_response:
                        content = json_response['message'].get('content', '')
                        full_response += content
                        # Update console in the main thread
                        sublime.set_timeout(
                            lambda c=content: self.console.run_command('append', {'characters': c}),
                            0
                        )

            return [full_response]

        except Exception as e:
            sublime.error_message(f"Error: {str(e)}")
            return []

    def generate_completions_async(self, context):
        # Start a new thread for completion generation
        thread = threading.Thread(
            target=self._generate_completions_thread,
            args=(context,)
        )
        thread.start()

        # Show a loading indicator
        self.view.set_status('completion_status', 'Generating completions...')

        # Start checking for completion in a non-blocking way
        sublime.set_timeout(self._check_completion_ready, 100)

    def _generate_completions_thread(self, context):
        with self.lock:
            try:
                self.current_completions = self.get_completion(context)
            finally:
                self.completion_ready.set()

    def _check_completion_ready(self):
        if self.completion_ready.is_set():
            self.view.erase_status('completion_status')
            self.completion_ready.clear()
            self.current_completions = None
        else:
            sublime.set_timeout(self._check_completion_ready, 100)
