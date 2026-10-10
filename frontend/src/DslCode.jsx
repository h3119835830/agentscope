import React from 'react';
export function DslCode({text,firstLine=1}){
 const tokens=line=>line.split(/(#[^\n]*|"(?:\\.|[^"\\])*"|\b(?:source|rule|block|kill|notify|if|unless|after|since|because|and|or|not|exec|file|endpoint|read|write|unlink|connect|recv|open|exits|declassify|endorse|via|lineageIncludes)\b)/g).map((part,i)=><span key={i} className={part.startsWith('#')?'dsl-comment':part.startsWith('"')?'dsl-string':/^[a-zA-Z]+$/.test(part)?'dsl-keyword':''}>{part}</span>);
 return <div className="dsl-code" tabIndex={0} aria-label="ActPlane DSL">{(text||'未记录').split('\n').map((line,i)=><div className="dsl-code-line" key={i}><span className="dsl-line-number" aria-hidden="true">{firstLine+i}</span><code>{tokens(line)||' '}</code></div>)}</div>;
}
