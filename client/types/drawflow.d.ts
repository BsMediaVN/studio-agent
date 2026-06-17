declare module 'drawflow' {
  export default class Drawflow {
    constructor(container: HTMLElement);
    reroute: boolean;
    start(): void;
    addNode(
      name: string,
      inputs: number,
      outputs: number,
      x: number,
      y: number,
      className: string,
      data: Record<string, unknown>,
      html: string,
    ): number;
    addConnection(
      outputId: number,
      inputId: number,
      outputClass: string,
      inputClass: string,
    ): void;
    export(): Record<string, unknown>;
    import(data: Record<string, unknown>): void;
    destroy(): void;
  }
}

declare module 'drawflow/dist/drawflow.min.css' {
  const content: string;
  export default content;
}
