class CurlCffi < Formula
  include Language::Python::Virtualenv

  desc "HTTP client CLI with browser impersonation support"
  homepage "https://github.com/lexiforest/curl_cffi"
  url "https://files.pythonhosted.org/packages/48/5b/89fcfebd3e5e85134147ac99e9f2b2271165fd4d71984fc65da5f17819b7/curl_cffi-0.15.0.tar.gz"
  version "0.15.0"
  sha256 "ea0c67652bf6893d34ee0f82c944f37e488f6147e9421bef1771cc6545b02ded"
  license "MIT"

  depends_on "certifi" => :no_linkage
  depends_on "cffi" => :no_linkage
  depends_on :macos
  depends_on "python3"

  pypi_packages package_name:     "curl-cffi",
                exclude_packages: %w[certifi cffi]

  # For curl-cffi, we actually download the binaries even when using source dist,
  # There is really no need to use the tarball and build on user's machine.
  if %w[arm64 aarch64].include?(RbConfig::CONFIG["host_cpu"])
    resource "curl-cffi" do
      url "https://files.pythonhosted.org/packages/83/2d/3915e238579b3c5a92cead5c79130c3b8d20caaba7616cc4d894650e1d6b/curl_cffi-0.15.0-cp310-abi3-macosx_11_0_arm64.whl"
      sha256 "a25620d9bf989c9c029a7d1642999c4c265abb0bad811deb2f77b0b5b2b12e5b"
    end
  else
    resource "curl-cffi" do
      url "https://files.pythonhosted.org/packages/5e/42/54ddd442c795f30ce5dd4e49f87ce77505958d3777cd96a91567a3975d2a/curl_cffi-0.15.0-cp310-abi3-macosx_10_9_x86_64.whl"
      sha256 "bda66404010e9ed743b1b83c20c86f24fe21a9a6873e17479d6e67e29d8ded28"
    end
  end

  resource "markdown-it-py" do
    url "https://files.pythonhosted.org/packages/5b/f5/4ec618ed16cc4f8fb3b701563655a69816155e79e24a17b651541804721d/markdown_it_py-4.0.0.tar.gz"
    sha256 "cb0a2b4aa34f932c007117b194e945bd74e0ec24133ceb5bac59009cda1cb9f3"
  end

  resource "mdurl" do
    url "https://files.pythonhosted.org/packages/d6/54/cfe61301667036ec958cb99bd3efefba235e65cdeb9c84d24a8293ba1d90/mdurl-0.1.2.tar.gz"
    sha256 "bb413d29f5eea38f31dd4754dd7377d4465116fb207585f97bf925588687c1ba"
  end

  resource "pygments" do
    url "https://files.pythonhosted.org/packages/c3/b2/bc9c9196916376152d655522fdcebac55e66de6603a76a02bca1b6414f6c/pygments-2.20.0.tar.gz"
    sha256 "6757cd03768053ff99f3039c1a36d6c0aa0b263438fcab17520b30a303a82b5f"
  end

  resource "rich" do
    url "https://files.pythonhosted.org/packages/b3/c6/f3b320c27991c46f43ee9d856302c70dc2d0fb2dba4842ff739d5f46b393/rich-14.3.3.tar.gz"
    sha256 "b8daa0b9e4eef54dd8cf7c86c03713f53241884e814f4e2f5fb342fe520f639b"
  end

  def install
    python3 = "python3"
    venv = virtualenv_create(libexec, python3)
    venv.pip_install resources

    resource("curl-cffi").fetch
    args = std_pip_args(prefix: false, build_isolation: false).reject { |s| s == "--no-binary=:all:" }
    system python3, "-m", "pip", "--python=#{venv.root}/bin/python",
                          "install", *args, resource("curl-cffi").cached_download

    bin.install_symlink libexec/"bin/curl-cffi"
  end

  test do
    assert_match "curl-cffi", shell_output("#{bin}/curl-cffi --help")
  end
end
