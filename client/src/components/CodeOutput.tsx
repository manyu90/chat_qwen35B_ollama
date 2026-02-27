import { useState } from 'react';
import type { SSECodeOutput } from '../types';

interface CodeOutputProps {
  output: SSECodeOutput;
}

export default function CodeOutput({ output }: CodeOutputProps) {
  const [isExpanded, setIsExpanded] = useState(true);

  return (
    <div className="code-output-block">
      <div
        className="code-output-header"
        onClick={() => setIsExpanded(!isExpanded)}
      >
        <span className={`code-output-chevron ${isExpanded ? 'expanded' : ''}`}>
          &#9654;
        </span>
        <span className="code-output-label">
          {output.success ? 'Code executed successfully' : 'Code execution failed'}
        </span>
        <span className={`code-output-status ${output.success ? 'success' : 'failure'}`}>
          {output.success ? '\u2713' : '\u2717'}
        </span>
      </div>

      {isExpanded && (
        <div className="code-output-code">
          <pre><code>{output.code}</code></pre>
        </div>
      )}

      {output.stdout && (
        <div className="code-output-stdout">
          <div className="code-output-section-label">Output</div>
          <pre>{output.stdout}</pre>
        </div>
      )}

      {output.stderr && (
        <div className="code-output-stderr">
          <div className="code-output-section-label">Error</div>
          <pre>{output.stderr}</pre>
        </div>
      )}

      {output.images.length > 0 && (
        <div className="code-output-images">
          {output.images.map((url, i) => (
            <img
              key={i}
              src={url}
              alt={`Plot ${i + 1}`}
              className="code-output-image"
            />
          ))}
        </div>
      )}
    </div>
  );
}
