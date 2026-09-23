import { Component } from "react";

/** Last line of defence: an unexpected render error shows a recovery message instead of a blank page. */
export default class ErrorBoundary extends Component {
  state = { error: null };

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error, info) {
    console.error("Unhandled UI error", error, info?.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div className="fatal" role="alert">
        <h1>Something went wrong</h1>
        <p>This page hit an unexpected error. Anything you already submitted is saved. Reload the page to carry on.</p>
        <p>
          <button className="btn btn-primary" onClick={() => window.location.reload()}>Reload the page</button>{" "}
          <a className="btn" href="/">Go to the home page</a>
        </p>
      </div>
    );
  }
}
