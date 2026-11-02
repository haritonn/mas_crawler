use serde::Deserialize;

#[derive(Debug, Deserialize)]
pub struct Document {
    pub url: String,
    pub title: String,
    pub text: String,
}
