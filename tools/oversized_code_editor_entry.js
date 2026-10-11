// CodeMirror 6 virtualizes enormous single fenced Markdown blocks.
// Never mount a multi-megabyte code fence in Milkdown / ProseMirror.
import {EditorState} from '@codemirror/state';
import {EditorView, basicSetup} from 'codemirror';
import {oneDark} from '@codemirror/theme-one-dark';

function createBlockEditor(root, content, onChange){
  const state=EditorState.create({
    doc:content,
    extensions:[
      basicSetup,
      oneDark,
      EditorView.lineWrapping,
      EditorView.updateListener.of(update=>{if(update.docChanged)onChange();}),
    ],
  });
  const view=new EditorView({state,parent:root});
  return {
    getContent(){return view.state.doc.toString();},
    focus(){view.focus();},
    destroy(){view.destroy();},
    getViewport(){return view.viewport;},
  };
}
window.LanternLargeBlockEditor={createBlockEditor};
