use thiserror::Error;

#[derive(Debug, Error)]
pub enum ExtractError {
    #[error("invalid CSS selector {selector:?}: {message}")]
    InvalidSelector { selector: String, message: String },

    #[error("no elements matching {field} selector")]
    NoMatch { field: &'static str },

    #[error("extracted content is empty")]
    EmptyContent,
}

#[derive(Debug, Error)]
pub enum LinkError {
    #[error("invalid page URL {url:?}: {source}")]
    InvalidPageUrl {
        url: String,
        #[source]
        source: url::ParseError,
    },

    #[error("unsupported page URL scheme {scheme:?}; expected HTTP or HTTPS")]
    UnsupportedPageScheme { scheme: String },
}
