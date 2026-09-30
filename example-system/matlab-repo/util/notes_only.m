function notes_only()
%NOTES_ONLY Exercises the tokenizer: nothing below the comment block is a real call.
%{
    fake_call_in_block_comment(1);
    another_fake(2)
%}
msg = 'string_call(3) is text, not a call';
msg2 = "so is double_quoted(4)";
x = [1 2 3]';                      % transpose, not a string start
disp(msg); disp(msg2); disp(x');   % disp is the only call here
end
